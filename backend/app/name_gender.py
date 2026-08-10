import re
import math
from collections import defaultdict
from dataclasses import dataclass


MALE = {
    "abdul", "achmad", "aditya", "agus", "ahmad", "akbar", "aldi", "andra", "andri",
    "andi", "arif", "arya", "bagas", "bambang", "bayu", "bima", "budi", "dedi", "deni", "dimas",
    "eko", "fajar", "fauzan", "ferdi", "firmansyah", "gunawan", "hadi", "hendri", "herman", "ilham",
    "imam", "irfan", "joko", "muhamad", "muhammad", "nurhadi", "putra", "rafi", "rahmat", "ramadhan",
    "pranata", "rangga", "reynaldi", "ridho", "rizal", "rizki", "saputra", "syahrul", "teguh", "wahyudi", "zulkifli",
}
FEMALE = {
    "aisyah", "anisa", "annisa", "ayu", "bella", "cahyaning", "dewi", "fitri", "fitria", "indah",
    "cahyani", "dian", "kartika", "khairunnisa", "laila", "lestari", "maharani", "melati", "mutiara", "nadia", "nabila", "novita",
    "nuraini", "nurhayati", "nurul", "permata", "putri", "rahma", "rahmi", "ramadhani", "ratna", "rina", "safitri", "salsabila", "sari",
    "siti", "sri", "syafitri", "tiara", "vina", "wulandari", "yanti", "yuliana", "zahra", "zahrani",
}
MALE_SUFFIXES = ("syah", "wan", "man", "din")
FEMALE_SUFFIXES = ("wati", "ningsih", "sari", "lesti", "riana", "yanti")
NEUTRAL = {"dwi", "eka", "tri", "nur", "cahya", "fitra", "rahayu", "wahyu", "agung"}
NAME_OVERRIDES = {
    "abd rahman ibrahim": "Laki-laki",
    "abd rahman abdullah": "Laki-laki",
    "abd wahit mantali": "Laki-laki",
    "adawiya ui": "Perempuan",
    "adelfin abas": "Perempuan",
    "adelia oktaviani luiti": "Perempuan",
    "adi prasatya dumbi": "Laki-laki",
    "adi zulkarnain koniyo": "Laki-laki",
    "aditia walangadi": "Laki-laki",
    "agustina uti": "Perempuan",
    "aida habuke": "Perempuan",
    "aira cahaya bintang kaluku": "Perempuan",
}


@dataclass(frozen=True)
class GenderEstimate:
    label: str | None
    confidence: float


def name_tokens(name: str | None) -> list[str]:
    return [token for token in re.findall(r"[a-z]+", (name or "").lower()) if len(token) > 1]


def estimate_gender(name: str | None) -> GenderEstimate:
    tokens = name_tokens(name)
    normalized = " ".join(tokens)
    if normalized in NAME_OVERRIDES:
        return GenderEstimate(NAME_OVERRIDES[normalized], 1.0)
    if "permata" in tokens or (tokens and tokens[0] == "nurul"):
        return GenderEstimate("Perempuan", .95)
    male = female = 0.0
    for index, token in enumerate(tokens):
        weight = 1.3 if index == 0 else 1.0
        if token in MALE:
            male += 2.5 * weight
        if token in FEMALE:
            female += 2.5 * weight
        if token not in NEUTRAL and len(token) >= 5:
            if token.endswith(MALE_SUFFIXES):
                male += .65
            if token.endswith(FEMALE_SUFFIXES):
                female += .9
    total = male + female
    if total < 2.0 or abs(male - female) < 1.4:
        return GenderEstimate(None, 0.0 if not total else round(max(male, female) / total, 2))
    label = "Laki-laki" if male > female else "Perempuan"
    confidence = min(.98, .65 + abs(male - female) / max(total, 1) * .3)
    return GenderEstimate(label, round(confidence, 2))


class AdaptiveGenderClassifier:
    """School-local classifier trained from verified and operator-labelled full names."""

    def __init__(self, samples: list[tuple[str, str]]) -> None:
        self.first_counts: dict[str, dict[str, float]] = defaultdict(lambda: {"Laki-laki": 0.0, "Perempuan": 0.0})
        self.operator_first: dict[str, dict[str, float]] = defaultdict(lambda: {"Laki-laki": 0.0, "Perempuan": 0.0})
        for name, label in samples:
            if label not in {"Laki-laki", "Perempuan"}:
                continue
            tokens = name_tokens(name)
            if not tokens:
                continue
            self.first_counts[tokens[0]][label] += 1
            if " ".join(tokens) in NAME_OVERRIDES:
                self.operator_first[tokens[0]][label] += 1

    def predict(self, name: str | None) -> GenderEstimate:
        tokens = name_tokens(name)
        normalized = " ".join(tokens)
        if normalized in NAME_OVERRIDES:
            return GenderEstimate(NAME_OVERRIDES[normalized], 1.0)
        if tokens:
            operator = self.operator_first.get(tokens[0])
            if operator:
                total = operator["Laki-laki"] + operator["Perempuan"]
                if total and min(operator.values()) == 0:
                    return GenderEstimate("Laki-laki" if operator["Laki-laki"] else "Perempuan", .98)
            observed = self.first_counts.get(tokens[0])
            if observed:
                total = observed["Laki-laki"] + observed["Perempuan"]
                majority = max(observed.values())
                if total >= 2 and majority / total >= .9:
                    return GenderEstimate("Laki-laki" if observed["Laki-laki"] > observed["Perempuan"] else "Perempuan", round(.85 + .1 * majority / total, 2))
        base = estimate_gender(name)
        return base


def operator_samples() -> list[tuple[str, str]]:
    return [(name, label) for name, label in NAME_OVERRIDES.items()]
