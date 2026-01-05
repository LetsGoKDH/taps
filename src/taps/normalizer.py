# =========================
# Korean text normalization v0.6.4 (STRUCTURAL FIX 3)
# =========================

import re
from collections import Counter
from datasets import load_dataset
from kiwipiepy import Kiwi

kiwi = Kiwi()

# Special marker for protected spaces
SPACE = "␣"  # U+2423

# -------------------------
# 0) Utilities
# -------------------------
def norm_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def is_hangul_only(token: str) -> bool:
    return bool(token) and re.fullmatch(r"[가-힣]+", token) is not None

def has_protected_space(token: str) -> bool:
    return SPACE in (token or "")

# punctuation -> space (avoid accidental concatenation)
# IMPORTANT: do NOT include middle dot '·' here; we delete it BEFORE this regex.
PUNCT_RE = re.compile(
    r'["\'\u201c\u201d\u2018\u2019`´•…(),;:!?{}\[\]<>]|[—–\-]|[/\\]|[|]|[""'']'
)

def strip_punct_to_space(s: str) -> str:
    # 1) delete middle dot first so "출·퇴근" -> "출퇴근", "민결·윤결" -> "민결윤결"
    s = (s or "").replace("·", "")
    # 2) other punctuations -> space
    s = PUNCT_RE.sub(" ", s)
    return norm_spaces(s)

# -------------------------
# 1) Number reading (Sino / Native) with SPACE marker
# -------------------------
DIG = ["영", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]

# Native (1~99-ish)
NATIVE_1_19 = {
    1: "한", 2: "두", 3: "세", 4: "네", 5: "다섯",
    6: "여섯", 7: "일곱", 8: "여덟", 9: "아홉",
    10: "열",
    11: f"열{SPACE}한", 12: f"열{SPACE}두", 13: f"열{SPACE}세", 14: f"열{SPACE}네",
    15: f"열{SPACE}다섯", 16: f"열{SPACE}여섯", 17: f"열{SPACE}일곱", 18: f"열{SPACE}여덟", 19: f"열{SPACE}아홉",
}
NATIVE_TENS = {
    20: "스물", 30: "서른", 40: "마흔", 50: "쉰",
    60: "예순", 70: "일흔", 80: "여든", 90: "아흔"
}

def read_sino_under_100(n: int):
    assert 0 <= n < 100
    if n < 10:
        return [DIG[n]]
    if 10 <= n < 20:
        if n == 10:
            return ["십"]
        return ["십", DIG[n-10]]  # 11~19 -> 십 일 / 십 이 ...
    tens = n // 10
    ones = n % 10
    out = [f"{DIG[tens]}십"]      # 20~ -> 이십/삼십... (붙임)
    if ones:
        out.append(DIG[ones])
    return out

def read_sino_under_10000(n: int):
    assert 0 <= n < 10000
    tokens = []
    thou = n // 1000
    hund = (n % 1000) // 100
    rest = n % 100

    if thou:
        tokens.append("천" if thou == 1 else f"{DIG[thou]}천")
    if hund:
        tokens.append("백" if hund == 1 else f"{DIG[hund]}백")
    if rest:
        tokens += read_sino_under_100(rest)
    if not tokens:
        tokens = ["영"]
    return tokens

BIG_UNITS = [
    (10**16, "경"),
    (10**12, "조"),
    (10**8, "억"),
    (10**4, "만"),
    (1, ""),
]

def read_sino(n: int) -> str:
    if n == 0:
        return "영"
    if n < 0:
        return f"마이너스{SPACE}{read_sino(-n)}"
    tokens = []
    x = n
    for base, name in BIG_UNITS:
        q = x // base
        x = x % base
        if q == 0:
            continue
        tokens += read_sino_under_10000(q)
        if name:
            tokens.append(name)
    return SPACE.join(tokens)

def read_native(n: int) -> str:
    if n <= 0:
        return read_sino(n)
    if n in NATIVE_1_19:
        return NATIVE_1_19[n]
    if n < 100:
        tens = (n // 10) * 10
        ones = n % 10
        if tens in NATIVE_TENS:
            if ones == 0:
                return NATIVE_TENS[tens]
            return f"{NATIVE_TENS[tens]}{SPACE}{NATIVE_1_19[ones]}"
    return read_sino(n)

def read_digits_each(s: str) -> str:
    return SPACE.join(DIG[int(ch)] for ch in s)

def read_hour_native(n: int) -> str:
    # 1~12시는 고유어
    if 1 <= n <= 12:
        return read_native(n)
    return read_sino(n)

# -------------------------
# 2) English letters -> Hangul
# -------------------------
ALPHA = {
    "A": "에이", "B": "비", "C": "씨", "D": "디", "E": "이", "F": "에프", "G": "지",
    "H": "에이치", "I": "아이", "J": "제이", "K": "케이", "L": "엘", "M": "엠", "N": "엔",
    "O": "오", "P": "피", "Q": "큐", "R": "알", "S": "에스", "T": "티", "U": "유", "V": "브이",
    "W": "더블유", "X": "엑스", "Y": "와이", "Z": "지"
}
ENG_RE = re.compile(r"[A-Za-z]+")

def replace_english(text: str) -> str:
    """
    NOTE:
    - 'km' is a unit and MUST be handled only in numeric+unit stage as '키로미터'.
      Therefore, leave exact 'km' untouched here.
    - tokens like 'pokm' should still be spelled out => 피오케이엠
    """
    def _rep(m):
        w = m.group(0)
        # exact unit token exceptions (safe)
        if w.lower() == "km":
            return w
        return "".join(ALPHA.get(ch.upper(), ch) for ch in w)
    return ENG_RE.sub(_rep, text or "")

# -------------------------
# 3) Symbols
# -------------------------
def replace_symbols(text: str) -> str:
    t = text or ""
    t = t.replace("℃", "도씨")
    t = t.replace("%", f"{SPACE}퍼센트{SPACE}")
    t = t.replace("°", f"{SPACE}도{SPACE}")

    # unicode km symbol (겉으로는 km처럼 보이지만 영문 정규식에 안 걸릴 수 있음)
    t = t.replace("㎞", "km")
    return t

# -------------------------
# 4) COVID-19 (priority)
# -------------------------
def replace_covid(text: str) -> str:
    t = text or ""
    t = re.sub(r"코로나\s*19\b", f"코로나{SPACE}일구", t)
    t = re.sub(r"COVID\s*[-–]?\s*19\b", f"코로나{SPACE}일구", t, flags=re.IGNORECASE)
    return t

# -------------------------
# 5) A씨/B씨 spacing EARLY
# -------------------------
SSI_FOLLOW = r"(?:\s|$|[을를은는이가에의과와도만부터까지에서에게께서으로로]|[.,;:!?])"
ABC_SSI_RE = re.compile(rf"([가-힣]{{1,4}})씨(?={SSI_FOLLOW})")

def fix_ssi_early(s: str) -> str:
    return ABC_SSI_RE.sub(rf"\1{SPACE}씨", s or "")

# -------------------------
# 6) Numbers + Units (CRITICAL)
#   - FIX: never eat whitespace after unit unless tail actually matches
#   - ADD: km canonicalization, bigunit+unit2, mixed-man notation
# -------------------------
NATIVE_UNITS = {"개","명","곳","칸","번","시간","살","마리","권","장"}

UNITS_ALL = [
    # counters
    "개조","개","명","곳","칸","대","번","시간","살","마리","권","장",
    # time/date
    "년","월","일","시","분","초",
    # metric/money
    "퍼센트","도씨","도",
    "키로미터","킬로미터","미터","km",
    "원","세",
    # task-specific
    "부","회",
]
_units_sorted = sorted(UNITS_ALL, key=len, reverse=True)
UNITS_ALT = "|".join(map(re.escape, _units_sorted))

TRAIL_PARTS = [
    "께서","에서","에게","으로","부터","까지",
    "은","는","이","가","을","를","에","로","과","와","도","만","의",
]
TRAIL_SUFFIXES = ["인"]
TAIL_ALT = "|".join(map(re.escape, sorted(TRAIL_PARTS + TRAIL_SUFFIXES, key=len, reverse=True)))

# FIXED REGEXES:
# - move \s* into optional tail group: (?:\s*(TAIL))?
DEC_UNIT_RE = re.compile(rf"(\d[\d,]*)\.(\d+)\s*({UNITS_ALT})(?:\s*({TAIL_ALT}))?")
APPROX_RE   = re.compile(rf"(\d[\d,]*)\s*(천|만|억|조)\s*여\s*({UNITS_ALT})?(?:\s*({TAIL_ALT}))?")
INT_UNIT_RE = re.compile(rf"(\d[\d,]*)\s*({UNITS_ALT})(?:\s*({TAIL_ALT}))?")

# NEW: mixed '만' notation with a unit: 5만1300명, 2만 500명 ...
MIXED_MAN_UNIT_RE = re.compile(rf"(\d[\d,]*)\s*만\s*(\d[\d,]*)\s*({UNITS_ALT})(?:\s*({TAIL_ALT}))?")

# NEW: bigunit+unit2 (e.g., 350억원, 12만명, 3천원)
# unit2 scope: keep small and safe (expand if needed)
BIGUNIT_UNIT2 = r"(?:원|명|개|곳|칸|대|번|시간|살|마리|권|장|회|부)"
BIGUNIT_RE = re.compile(rf"(\d[\d,]*)\s*(천|만|억|조)\s*({BIGUNIT_UNIT2})(?:\s*({TAIL_ALT}))?")

def canon_unit(u: str) -> str:
    if not u:
        return u
    if u.lower() == "km":
        return "키로미터"
    return u

def normalize_numbers_units(text: str) -> str:
    t = text or ""

    # (0) COVID first
    t = replace_covid(t)

    # (A) Decimal + unit
    def _rep_dec(m):
        ip = int(m.group(1).replace(",", ""))
        fp = m.group(2)
        unit = canon_unit(m.group(3))
        tail = m.group(4) or ""
        return f"{read_sino(ip)}{SPACE}점{SPACE}{read_digits_each(fp)}{SPACE}{unit}{tail}"
    t = DEC_UNIT_RE.sub(_rep_dec, t)

    # (B) Approx (여)
    def _rep_approx(m):
        num = int(m.group(1).replace(",", ""))
        big = m.group(2)
        unit = canon_unit(m.group(3) or "")
        tail = m.group(4) or ""
        if unit:
            return f"{read_sino(num)}{SPACE}{big}{SPACE}여{unit}{tail}"
        return f"{read_sino(num)}{SPACE}{big}{SPACE}여{tail}"
    t = APPROX_RE.sub(_rep_approx, t)

    # (B2) Mixed-man notation with unit: 5만1300명 -> (5*10000+1300)명
    def _rep_mixed_man(m):
        a = int(m.group(1).replace(",", ""))
        b = int(m.group(2).replace(",", ""))
        unit = canon_unit(m.group(3))
        tail = m.group(4) or ""
        total = a * 10000 + b

        # use the same unit reading policy as INT_UNIT
        if unit == "시":
            return f"{read_hour_native(total)}{SPACE}{unit}{tail}"
        if unit == "대":
            reading = read_sino(total) if total >= 10 else read_native(total)
            return f"{reading}{SPACE}{unit}{tail}"
        if unit in NATIVE_UNITS:
            return f"{read_native(total)}{SPACE}{unit}{tail}"
        return f"{read_sino(total)}{SPACE}{unit}{tail}"

    t = MIXED_MAN_UNIT_RE.sub(_rep_mixed_man, t)

    # (B3) bigunit+unit2: 350억원 -> 삼백 오십 억 원
    def _rep_bigunit(m):
        num = int(m.group(1).replace(",", ""))
        big = m.group(2)
        unit2 = m.group(3)
        tail = m.group(4) or ""
        return f"{read_sino(num)}{SPACE}{big}{SPACE}{unit2}{tail}"

    t = BIGUNIT_RE.sub(_rep_bigunit, t)

    # (C) Special patterns (ONLY digits-context)
    t = re.sub(
        rf"형사\s*(\d[\d,]*)\s*부(?:\s*({TAIL_ALT}))?",
        lambda m: f"형사{SPACE}{read_sino(int(m.group(1).replace(',','')))}{ SPACE}부{(m.group(2) or '')}",
        t
    )

    t = re.sub(
        rf"제\s*(\d[\d,]*)\s*회(?:\s*({TAIL_ALT}))?",
        lambda m: f"제{SPACE}{read_sino(int(m.group(1).replace(',','')))}{ SPACE}회{(m.group(2) or '')}",
        t
    )

    # (D) General INT+UNIT (with tail)
    def _rep_int_unit(m):
        n = int(m.group(1).replace(",", ""))
        unit = canon_unit(m.group(2))
        tail = m.group(3) or ""

        if unit == "시":
            return f"{read_hour_native(n)}{SPACE}{unit}{tail}"

        if unit == "대":
            reading = read_sino(n) if n >= 10 else read_native(n)
            return f"{reading}{SPACE}{unit}{tail}"

        if unit in NATIVE_UNITS:
            return f"{read_native(n)}{SPACE}{unit}{tail}"

        return f"{read_sino(n)}{SPACE}{unit}{tail}"

    t = INT_UNIT_RE.sub(_rep_int_unit, t)

    # (E) remaining integers
    t = re.sub(r"\d[\d,]*", lambda m: read_sino(int(m.group(0).replace(",", ""))), t)

    return norm_spaces(t)

# -------------------------
# 7) Compound spacing (RULES + Kiwi), with particle detach/reattach
# -------------------------
# IMPORTANT: reduce forced suffix splitting to avoid breaking proper noun org/facility names
FORCE_SUFFIX_SPLIT = [
    "체육공원",       # your critical request
    "운송사업조합",   # (kept if needed)
]

# Org/facility tails that should NOT be split when preceded by short place prefix
NO_SPLIT_TAILS = {
    "체육회","협회","위원회","공사","센터",
    "국민체육센터","장애인체육관","체육센터",
}

# Avoid Kiwi on derivational endings
PROTECT_SUFFIXES_NO_KIWI = ("적으로", "적인", "하기로", "하기", "하게", "하며", "했다", "한다", "됩니다", "였다", "이었다", "이었", "했다")

TRAIL_PARTS_ONLY = [
    "께서","에서","에게","으로","부터","까지",
    "은","는","이","가","을","를","에","로","과","와","도","만","의",
]
TRAIL_PART_RE = re.compile(
    rf"^([가-힣]{{2,}})({ '|'.join(map(re.escape, sorted(TRAIL_PARTS_ONLY, key=len, reverse=True))) })$".replace(" ", "")
)

def split_trailing_particle(tok: str):
    if not is_hangul_only(tok):
        return tok, ""
    m = TRAIL_PART_RE.fullmatch(tok)
    if not m:
        return tok, ""
    return m.group(1), m.group(2)

def attach_particle(spaced_stem: str, particle: str) -> str:
    if not particle:
        return spaced_stem
    parts = spaced_stem.split()
    if not parts:
        return particle
    parts[-1] = parts[-1] + particle
    return " ".join(parts)

def split_by_suffix_boundary(stem: str) -> str:
    for suf in FORCE_SUFFIX_SPLIT:
        if stem.endswith(suf) and len(stem) > len(suf) + 1:
            pre = stem[:-len(suf)]
            if len(pre) >= 2:
                return pre + " " + suf
    return stem

def split_forest_like(stem: str) -> str:
    # 자작나무숲/잣나무숲 -> 자작나무 숲
    if stem.endswith("숲") and len(stem) >= 3:
        pre = stem[:-1]
        if len(pre) >= 2:
            return pre + " 숲"
    return stem

BAD_1CHAR_SEGMENTS = {
    "제",
    "회","원","장","부","시","군","구","면","리","동","법","안",
    "은","는","이","가","을","를","에","의","로","과","와","도","만",
}

ADMIN_SUFFIX = {"시","군","구","읍","면","리","동"}

SPORT_CORE = {"배드민턴"}  # 최소 범위로 시작 (필요 시 확대)

def accept_kiwi_split(original: str, spaced: str) -> bool:
    if spaced == original:
        return False
    parts = spaced.split()
    if "".join(parts) != original:
        return False

    # (1) reject 1-char segments (except final '숲')
    for i, p in enumerate(parts):
        if len(p) == 1:
            if not (i == len(parts)-1 and p == "숲"):
                return False
        if p in BAD_1CHAR_SEGMENTS:
            return False

    # (2) prevent splitting administrative suffix (부천 시 ...)
    if parts and parts[-1] in ADMIN_SUFFIX:
        return False

    # (3) legal terms
    if "법" in original:
        return False

    # (4) keep '*길' glued
    if len(parts) == 2 and parts[-1] == "길" and len(parts[0]) >= 2:
        return False

    # (5) cap aggressiveness
    if len(parts) >= 4:
        return False

    # (6) block splitting of place+org/facility proper nouns
    # e.g., 순창군체육회 -> 순창군 체육회 (reject)
    if len(parts) == 2 and parts[-1] in NO_SPLIT_TAILS:
        head = parts[0]
        if len(head) <= 3 or (head and head[-1] in ADMIN_SUFFIX):
            return False

    # (7) block sport tournament splitting: 전국 배드민턴 대회 (reject)
    if original.endswith("대회") and any(x in original for x in SPORT_CORE):
        return False

    return True

def apply_compound_spacing(text: str, use_kiwi: bool = True, min_len: int = 5) -> str:
    tokens = (text or "").split()
    out = []

    for tok in tokens:
        # Skip tokens containing SPACE marker
        if has_protected_space(tok):
            out.append(tok)
            continue

        # fixed rule
        if tok == "빈차":
            out.append("빈 차")
            continue

        stem, particle = split_trailing_particle(tok)

        if is_hangul_only(stem):
            # "X배" (cup) split: do it without blocking Kiwi split of prefix
            cup_suffix = ""
            if stem.endswith("배") and len(stem) >= 4:
                pre = stem[:-1]
                # avoid numeric multipliers: 2배, 세배, 열배 ...
                if not re.fullmatch(r"(?:\d+|[한두세네다섯여섯일곱여덟아홉열]+)", pre):
                    stem = pre
                    cup_suffix = "배"

            if len(stem) >= min_len:
                s1 = split_by_suffix_boundary(stem)
                if " " not in s1:
                    s1 = split_forest_like(s1)

                if " " in s1:
                    spaced = s1
                else:
                    if use_kiwi and not stem.endswith(PROTECT_SUFFIXES_NO_KIWI):
                        spaced_k = kiwi.space(stem)
                        spaced = spaced_k if accept_kiwi_split(stem, spaced_k) else stem
                    else:
                        spaced = stem

                # re-append cup suffix if applied
                if cup_suffix:
                    spaced = spaced + " " + cup_suffix

                out.append(attach_particle(spaced, particle))
            else:
                # still may need to apply cup suffix split for short stems
                if cup_suffix:
                    out.append(attach_particle(stem + " " + cup_suffix, particle))
                else:
                    out.append(tok)
        else:
            out.append(tok)

    return norm_spaces(" ".join(out))

# -------------------------
# 8) Post fixes
# -------------------------
PARTICLE_JOIN_RE = re.compile(
    r"(\S+)\s+(을|를|은|는|이|가|에|에서|에게|께서|으로|로|과|와|도|만|부터|까지|의)\b"
)

def join_particles(s: str) -> str:
    cur = s or ""
    for _ in range(3):
        nxt = PARTICLE_JOIN_RE.sub(r"\1\2", cur)
        if nxt == cur:
            break
        cur = nxt
    return cur

def final_glue_fixes(s: str) -> str:
    t = s or ""
    t = t.replace("이 번", "이번")
    t = t.replace("저 번", "저번")
    return norm_spaces(t)

def restore_protected_spaces(s: str) -> str:
    return (s or "").replace(SPACE, " ")

# -------------------------
# 9) Main normalize
# -------------------------
def normalize_v064(raw: str, use_kiwi_for_compounds: bool = True, debug: bool = False) -> str:
    if raw is None:
        raw = ""

    t = raw
    if debug: print("[raw]", t)

    # 1) symbols, english
    t = replace_symbols(t)
    t = replace_english(t)
    if debug: print("[sym/eng]", t)

    # 2) SSI early
    t = fix_ssi_early(t)
    if debug: print("[ssi]", t)

    # 3) numbers+units (SPACE markers)
    t = normalize_numbers_units(t)
    if debug: print("[num/unit]", t)

    # 4) punctuation -> space (middle dot already deleted)
    t = strip_punct_to_space(t)
    if debug: print("[punct]", t)

    # 5) compound spacing (particle-safe)
    t = apply_compound_spacing(t, use_kiwi=use_kiwi_for_compounds, min_len=5)
    if debug: print("[compound]", t)

    # 6) post fixes
    t = join_particles(t)
    t = final_glue_fixes(t)
    if debug: print("[post]", t)

    # 7) restore SPACE markers
    t = restore_protected_spaces(t)
    if debug: print("[final]", t)

    return t

# Backward alias (optional): keep old name for your pipeline calls
def normalize_v063(raw: str, use_kiwi_for_compounds: bool = True, debug: bool = False) -> str:
    return normalize_v064(raw, use_kiwi_for_compounds=use_kiwi_for_compounds, debug=debug)

# -------------------------
# 10) Evaluation helpers
# -------------------------
def canon_levels(s: str):
    c0 = s or ""
    c1 = PUNCT_RE.sub("", c0).replace("·", "")
    c2 = norm_spaces(c1)
    c3 = re.sub(r"\s+", "", c2)
    return c0, c1, c2, c3

def evaluate(pred_fn, max_rows=200, show_mismatch=25):
    print("=" * 60)
    print("TAPS Test Set evaluation (v0.6.4)")
    print("=" * 60)

    ds = load_dataset(
        "yskim3271/Throat_and_Acoustic_Pairing_Speech_Dataset",
        name="with_normalized_text",
        split="test",
        streaming=True
    )

    c = Counter()
    mismatches = []

    for i, ex in enumerate(ds):
        raw = ex.get("text") or ""
        gold = ex.get("normalized_text") or ""
        pred = pred_fn(raw)

        g0, g1, g2, g3 = canon_levels(gold)
        p0, p1, p2, p3 = canon_levels(pred)

        c["rows"] += 1
        if re.search(r"\d", raw):
            c["has_digit"] += 1
        if re.search(r"[A-Za-z]", raw):
            c["has_english"] += 1
        if re.search(r"[^0-9A-Za-z가-힣\s]", raw):
            c["has_symbol"] += 1

        if p0 == g0: c["match_strict"] += 1
        if p1 == g1: c["match_punct"] += 1
        if p2 == g2: c["match_punct_space"] += 1
        if p3 == g3: c["match_no_space"] += 1

        if p0 != g0 and len(mismatches) < show_mismatch:
            mismatches.append((i, raw, gold, pred))

        if max_rows is not None and c["rows"] >= max_rows:
            break

    rows = c["rows"]
    print("\n=== summary ===")
    print(dict(c))
    print(f"strict: {c['match_strict']/rows:.3f}")
    print(f"punct: {c['match_punct']/rows:.3f}")
    print(f"punct+space: {c['match_punct_space']/rows:.3f}")
    print(f"no_space: {c['match_no_space']/rows:.3f}")

    print("\n=== mismatches (sample) ===")
    for i, raw, gold, pred in mismatches:
        print(f"\n[{i}] raw : {raw}\n gold: {gold}\n pred: {pred}")
