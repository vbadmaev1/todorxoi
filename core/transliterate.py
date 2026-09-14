# -*- coding: utf-8 -*-
"""
transliterate.py — загружает обученную модель кириллица -> транслитерация
и даёт функцию transliterate(text), которая работает и на отдельном слове,
и на целом предложении.

Как это устроено для предложений (модель обучена только на словах):
  1. Текст режется на "слова" (кириллица, дефис внутри слова не разделяет —
     как "Моңһл-Күрә") и "всё остальное" (пробелы, пунктуация, цифры) —
     второе не трогается.
  2. Для каждого слова: сперва точный словарь из чекпойнта (проверенные
     пары — надёжнее модели), если слова там нет — модель (обобщение на
     новые слова).
  3. Регистр (Заглавная / КАПС) восстанавливается отдельно — модель обучена
     только на строчных.

Отличие от исходного скрипта: модель грузится ЛЕНИВО (при первом вызове),
а путь к чекпойнту берётся из переменной окружения MODEL_PATH, чтобы бот
стартовал быстро и не падал на импорте.
"""

import os
import re
import threading
import unicodedata

import torch
import torch.nn as nn
import torch.nn.functional as F

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(_HERE), "model", "translit_model_cyr2lat.pt"
)
MODEL_PATH = os.environ.get("MODEL_PATH", _DEFAULT_MODEL_PATH)

PAD, SOS, EOS, UNK = "<pad>", "<s>", "</s>", "<unk>"


# =============================================================================
# Архитектура — должна совпадать с той, на которой чекпойнт обучался
# (BiGRU-энкодер + attention-декодер, посимвольно).
# =============================================================================

class _CharVocab:
    """Восстанавливается из уже готового списка символов (itos) в
    чекпойнте — обучать словарь заново не нужно."""

    def __init__(self, itos):
        self.itos = itos
        self.stoi = {ch: i for i, ch in enumerate(itos)}

    def __len__(self):
        return len(self.itos)

    def encode(self, word):
        ids = [self.stoi.get(ch, self.stoi[UNK]) for ch in word]
        ids = [self.stoi[SOS]] + ids + [self.stoi[EOS]]
        return torch.tensor(ids, dtype=torch.long)

    def decode(self, ids):
        chars = []
        for i in ids:
            ch = self.itos[i]
            if ch == EOS:
                break
            if ch in (PAD, SOS):
                continue
            chars.append(ch)
        return "".join(chars)


class _Encoder(nn.Module):
    def __init__(self, vocab_size, emb_dim, hid_dim, pad_idx):
        super().__init__()
        self.emb = nn.Embedding(vocab_size, emb_dim, padding_idx=pad_idx)
        self.gru = nn.GRU(emb_dim, hid_dim, batch_first=True, bidirectional=True)
        self.fc = nn.Linear(hid_dim * 2, hid_dim)

    def forward(self, src, src_lens):
        emb = self.emb(src)
        packed = nn.utils.rnn.pack_padded_sequence(
            emb, src_lens.cpu(), batch_first=True, enforce_sorted=False
        )
        packed_out, h = self.gru(packed)
        outputs, _ = nn.utils.rnn.pad_packed_sequence(packed_out, batch_first=True)
        h_cat = torch.cat([h[0], h[1]], dim=1)
        h0 = torch.tanh(self.fc(h_cat))
        return outputs, h0


class _Attention(nn.Module):
    def __init__(self, hid_dim):
        super().__init__()
        self.attn = nn.Linear(hid_dim * 3, hid_dim)
        self.v = nn.Linear(hid_dim, 1, bias=False)

    def forward(self, dec_hidden, enc_outputs, mask):
        S = enc_outputs.size(1)
        dec_rep = dec_hidden.unsqueeze(1).repeat(1, S, 1)
        energy = torch.tanh(self.attn(torch.cat([dec_rep, enc_outputs], dim=2)))
        scores = self.v(energy).squeeze(2)
        scores = scores.masked_fill(mask == 0, -1e10)
        return F.softmax(scores, dim=1)


class _Decoder(nn.Module):
    def __init__(self, vocab_size, emb_dim, hid_dim, pad_idx):
        super().__init__()
        self.emb = nn.Embedding(vocab_size, emb_dim, padding_idx=pad_idx)
        self.attention = _Attention(hid_dim)
        self.gru = nn.GRUCell(emb_dim + hid_dim * 2, hid_dim)
        self.out = nn.Linear(hid_dim * 3 + emb_dim, vocab_size)

    def forward(self, input_tok, hidden, enc_outputs, mask):
        emb = self.emb(input_tok)
        attn_weights = self.attention(hidden, enc_outputs, mask)
        context = torch.bmm(attn_weights.unsqueeze(1), enc_outputs).squeeze(1)
        gru_input = torch.cat([emb, context], dim=1)
        hidden = self.gru(gru_input, hidden)
        pred = self.out(torch.cat([hidden, context, emb], dim=1))
        return pred, hidden


class _Seq2Seq(nn.Module):
    def __init__(self, encoder, decoder, pad_idx, sos_idx, eos_idx, device):
        super().__init__()
        self.encoder = encoder
        self.decoder = decoder
        self.pad_idx = pad_idx
        self.sos_idx = sos_idx
        self.eos_idx = eos_idx
        self.device = device

    def make_mask(self, src):
        return (src != self.pad_idx).to(self.device)

    @torch.no_grad()
    def greedy_decode(self, src, src_lens, max_len):
        self.eval()
        B = src.size(0)
        enc_outputs, hidden = self.encoder(src, src_lens)
        mask = self.make_mask(src)
        input_tok = torch.full((B,), self.sos_idx, dtype=torch.long, device=self.device)
        results = [[] for _ in range(B)]
        finished = [False] * B
        for _ in range(max_len):
            pred, hidden = self.decoder(input_tok, hidden, enc_outputs, mask)
            input_tok = pred.argmax(1)
            for i in range(B):
                if not finished[i]:
                    tok = input_tok[i].item()
                    if tok == self.eos_idx:
                        finished[i] = True
                    else:
                        results[i].append(tok)
            if all(finished):
                break
        return results


# =============================================================================
# Ленивая загрузка модели — один раз на процесс, потокобезопасно.
# =============================================================================

class _Bundle:
    __slots__ = ("model", "src_vocab", "tgt_vocab", "max_len", "device", "dictionary")


_BUNDLE = None
_LOAD_LOCK = threading.Lock()
# torch на CPU по умолчанию жрёт все ядра; на маленьком VPS это только вредит
torch.set_num_threads(int(os.environ.get("TORCH_NUM_THREADS", "1")))


def _get_device():
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _load(model_path=None):
    model_path = model_path or MODEL_PATH
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"Чекпойнт модели не найден: {model_path}. "
            f"Положите translit_model_cyr2lat.pt в папку model/ "
            f"или укажите путь через переменную окружения MODEL_PATH."
        )
    device = _get_device()
    ckpt = torch.load(model_path, map_location=device, weights_only=False)

    src_vocab = _CharVocab(ckpt["src_vocab"])
    tgt_vocab = _CharVocab(ckpt["tgt_vocab"])
    pad_idx = src_vocab.stoi[PAD]
    emb_dim = ckpt["emb_dim"]
    hid_dim = ckpt["hid_dim"]
    max_len = ckpt.get("max_len", 32)

    encoder = _Encoder(len(src_vocab), emb_dim, hid_dim, pad_idx).to(device)
    decoder = _Decoder(len(tgt_vocab), emb_dim, hid_dim, pad_idx).to(device)
    model = _Seq2Seq(
        encoder, decoder, pad_idx,
        sos_idx=tgt_vocab.stoi[SOS], eos_idx=tgt_vocab.stoi[EOS], device=device,
    ).to(device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    bundle = _Bundle()
    bundle.model = model
    bundle.src_vocab = src_vocab
    bundle.tgt_vocab = tgt_vocab
    bundle.max_len = max_len
    bundle.device = device
    bundle.dictionary = ckpt.get("dictionary", {})
    return bundle


def get_bundle():
    """Возвращает загруженную модель (грузит при первом обращении)."""
    global _BUNDLE
    if _BUNDLE is None:
        with _LOAD_LOCK:
            if _BUNDLE is None:
                _BUNDLE = _load()
    return _BUNDLE


def warmup():
    """Прогрев: заранее загрузить модель и прогнать одно слово, чтобы
    первый пользователь не ждал загрузку чекпойнта."""
    transliterate_word("хальмг")


def model_info():
    b = get_bundle()
    return {
        "device": str(b.device),
        "dictionary_size": len(b.dictionary),
        "src_vocab": len(b.src_vocab),
        "tgt_vocab": len(b.tgt_vocab),
        "max_len": b.max_len,
        "model_path": MODEL_PATH,
    }


# =============================================================================
# Транслитерация одного слова
# =============================================================================

def transliterate_word(word):
    b = get_bundle()
    word = unicodedata.normalize("NFC", word)
    src_ids = b.src_vocab.encode(word).unsqueeze(0).to(b.device)
    src_lens = torch.tensor([src_ids.size(1)])
    pred_ids = b.model.greedy_decode(src_ids, src_lens, max_len=b.max_len)[0]
    return b.tgt_vocab.decode(pred_ids)


# =============================================================================
# Транслитерация предложения: токенизация + словарь/модель + регистр
# =============================================================================

_WORD_RE = re.compile(r"[а-яёәөүһҗңa-z]+(?:-[а-яёәөүһҗңa-z]+)*", re.IGNORECASE)

# Чем соединять части составного слова, разобранного по дефису.
# Обычный пробел: көвүн-күүкн — это два полноценных слова, и в письме они
# разделяются широким пробелом, а не узким неразрывным (узкий,  , у нас
# означает границу суффикса и получается из дефиса — см. translit_todo.py).
COMPOUND_JOINER = " "


def _restore_case(original_token, result):
    if original_token.isupper() and len(original_token) > 1:
        return result.upper()
    if original_token[:1].isupper():
        return result[:1].upper() + result[1:]
    return result


def _translit_token(token):
    """Одно «слово» из текста -> транслитерация. Возвращает (результат,
    откуда взялось): dict — точный словарь, split — составное слово,
    разобранное по дефису, model — предсказание модели."""
    b = get_bundle()
    key = unicodedata.normalize("NFC", token.lower())

    # 1. весь токен целиком есть в словаре — это самый надёжный ответ,
    #    в словаре уже лежат и зер-зев, и моңһл-күрә
    result = b.dictionary.get(key)
    if result is not None:
        return _restore_case(token, result), "dict"

    # 2. составное слово через дефис: көвүн-күүкн, эк-эцк, ах-дү.
    #    Модель на таком токене целиком выдаёт мусор (көвүн-күүкн ->
    #    köböüngöükken), а по частям всё чисто. Но делим ТОЛЬКО когда
    #    каждая часть сама по себе есть в словаре как самостоятельное
    #    слово — иначе так же разобрался бы и суффикс: в һазр-ән «ән»
    #    отдельным словом не существует, и целый токен модель обрабатывает
    #    правильно (γazar-bēn), а по частям вышло бы неверное γazar-ani.
    if "-" in key:
        parts = key.split("-")
        if len(parts) > 1 and all(p and p in b.dictionary for p in parts):
            joined = COMPOUND_JOINER.join(b.dictionary[p] for p in parts)
            return _restore_case(token, joined), "split"

    # 3. всё остальное — модель, на токене целиком (суффиксы через дефис
    #    попадают сюда и обрабатываются как надо)
    return _restore_case(token, transliterate_word(key)), "model"


def transliterate(text):
    """Транслитерирует кириллический текст (слово или целое предложение)
    в латиницу проекта. Пунктуация, пробелы, цифры остаются как есть."""
    return transliterate_with_stats(text)[0]


def transliterate_with_stats(text):
    """То же самое, но дополнительно возвращает статистику по источнику
    каждого слова: (результат, {"dict": n, "split": k, "model": m})."""
    out_parts = []
    stats = {"dict": 0, "split": 0, "model": 0}
    pos = 0
    for m in _WORD_RE.finditer(text):
        out_parts.append(text[pos:m.start()])
        piece, source = _translit_token(m.group())
        stats[source] += 1
        out_parts.append(piece)
        pos = m.end()
    out_parts.append(text[pos:])
    return "".join(out_parts), stats


if __name__ == "__main__":
    print("Информация о модели:", model_info())
    for w in ["альт", "тертцхн", "хальмг", "медвч"]:
        print(f"  {w} -> {transliterate_word(w)}")
    sentence = "Хальмг улс һазр-ән наран үдэ хәләҗи бәрдг."
    print("\nПредложение:")
    print(" ", sentence)
    print(" ", transliterate(sentence))
