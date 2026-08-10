import re
from collections import defaultdict
from dataclasses import dataclass


# Kamus nama depan Indonesia yang umum dipakai. Tidak lengkap (nama Indonesia
# sangat beragam lintas daerah/agama/budaya), tapi jauh lebih luas dari daftar
# awal supaya lebih sedikit nama yang jatuh ke "Belum dapat ditentukan".
MALE = {
    "abdul", "abdullah", "abdurrahman", "achmad", "adam", "adi", "aditya", "adnan", "afif", "agung",
    "agus", "ahmad", "aji", "akbar", "aldi", "aldo", "alfian", "alfiansyah", "ali", "alif", "amin",
    "anang", "andra", "andre", "andri", "andika", "andi", "angga", "anggara", "anwar", "ardi",
    "ardian", "ardiansyah", "arga", "aril", "arief", "arif", "arifin", "aris", "aryo", "arya",
    "asep", "aswin", "azhar", "bagas", "bagus", "bambang", "bayu", "bimo", "bima", "boy",
    "budi", "bustanul", "chandra", "dafa", "danang", "dandi", "daniel", "danu", "danang",
    "darma", "darmawan", "daud", "davin", "dedi", "deden", "dedy", "dendi", "deni", "denny",
    "denny", "dermawan", "dian", "didik", "didi", "dimas", "dion", "dodi", "doni", "donny",
    "doni", "duta", "eko", "elan", "endra", "endro", "erfan", "erik", "erick", "erlangga",
    "ervan", "erwin", "fadhil", "fadillah", "fadil", "faisal", "faiz", "fajar", "farhan",
    "fauzan", "fauzi", "febrian", "ferdi", "ferdinand", "fery", "firdaus", "firman", "firmansyah",
    "galang", "galih", "gerry", "gilang", "gunawan", "guntur", "hadi", "hafiz", "hafizh", "hakim",
    "hamdan", "hamzah", "hanif", "haris", "harsono", "harun", "hasan", "hasyim", "hendra",
    "hendrawan", "hendri", "hendro", "hendry", "heri", "herman", "hidayat", "hilman", "husein",
    "ibnu", "ibrahim", "iksan", "ikhsan", "ilham", "ilyas", "imam", "iman", "imron", "indra",
    "indrawan", "iqbal", "irawan", "irfan", "irham", "irsyad", "irwan", "iskandar", "ismail",
    "iswanto", "iwan", "jaka", "jamal", "jefri", "johan", "joko", "juanda", "junaidi", "juned",
    "kadek", "kamal", "karim", "kevin", "khairul", "komang", "kurnia", "kurniawan", "lukman",
    "made", "mahendra", "mahfud", "malik", "mamat", "marwan", "maulana", "maulid", "miftah",
    "misbah", "muchtar", "muhaimin", "muhamad", "muhammad", "mukhlis", "nanang", "narto",
    "naufal", "ngadiman", "nizam", "noval", "novan", "nugroho", "nugraha", "nur", "nurdin",
    "nurhadi", "nyoman", "oki", "okta", "pandu", "panji", "parman", "priyanto", "pranata",
    "prasetyo", "priyo", "purnomo", "putra", "rachmad", "rachman", "radit", "raditya", "rafael",
    "rafi", "rafly", "rahman", "rahmad", "rahmat", "raihan", "raka", "rama", "ramadhan", "rangga",
    "rasyid", "ravi", "raymond", "reihan", "renaldi", "reynaldi", "ricky", "ridho", "ridwan",
    "rifai", "rifki", "rio", "risky", "rivaldo", "rivai", "riyanto", "rizal", "rizki", "rizky",
    "robby", "robi", "roby", "rohman", "romi", "ronald", "ronny", "roni", "rudi", "rudy",
    "sahrul", "salim", "samsul", "sandi", "sandy", "santoso", "saputra", "septian", "setiawan",
    "setiyo", "sigit", "slamet", "soni", "subagio", "subur", "sugeng", "suhaimi", "suhardi",
    "sujarwo", "sukamto", "sukirno", "sulaiman", "supardi", "supriyanto", "surya", "susanto",
    "sutrisno", "sutopo", "syahid", "syahrizal", "syahrul", "syaiful", "syamsul", "syarif",
    "taufan", "taufik", "teddy", "teguh", "teuku", "tio", "tirta", "tomi", "tomy", "tony",
    "toto", "tri", "tulus", "umar", "usman", "vicky", "wahid", "wahyu", "wahyudi", "wawan",
    "widodo", "widianto", "wijaya", "wildan", "willy", "wira", "wisnu", "yadi", "yahya",
    "yanto", "yayan", "yoga", "yogi", "yudha", "yudi", "yudistira", "yudo", "yulianto",
    "yusuf", "yustinus", "zacky", "zaenal", "zaenudin", "zaidan", "zainal", "zainudin",
    "zaki", "zakaria", "zulfikar", "zulkarnain", "zulkifli",
}
FEMALE = {
    "adinda", "adelia", "adelina", "afifah", "aida", "aisyah", "alifia", "alika", "amanda",
    "amara", "amelia", "amelina", "andini", "anggi", "anggraeni", "anggraini", "angelina",
    "anisa", "anita", "annisa", "aprilia", "aprillia", "ari", "arum", "asri", "astrid", "astuti",
    "ayu", "ayudia", "ayunda", "azizah", "azzahra", "bela", "bella", "berliana", "bunga",
    "cahyani", "cahyaning", "cantika", "cindy", "citra", "clara", "danti", "desi", "desy",
    "devi", "devina", "dewi", "diah", "diana", "diani", "dian", "dinda", "dini", "diva",
    "dwi", "elisa", "elisabeth", "elvina", "endang", "erika", "erni", "eva", "evi", "farah",
    "farida", "fatimah", "fatma", "fauziah", "febi", "febrianti", "febriyanti", "fifi", "fina",
    "fitri", "fitria", "fitriani", "fitriyani", "gita", "hana", "hanifah", "hasna", "helena",
    "hesti", "ida", "ika", "iklima", "ima", "indah", "indriani", "intan", "irma", "isna",
    "juwita", "kania", "karina", "karmila", "kartika", "kasih", "kayla", "khadijah",
    "khairunnisa", "khoirunnisa", "laila", "laksmi", "lala", "lastri", "latifah", "laura",
    "lelia", "lestari", "lia", "lidya", "lilis", "lina", "linda", "listya", "lisa", "lita",
    "lusi", "lutfia", "maharani", "mala", "mardiana", "maria", "marlina", "marsha", "martha",
    "maya", "mayang", "mega", "megawati", "melani", "melati", "melinda", "mira", "mirna",
    "monica", "mulia", "murni", "mutia", "mutiara", "nabila", "nadhira", "nadia", "nadine",
    "nafisa", "naila", "nanda", "natalia", "natasya", "naura", "nazwa", "nia", "nila",
    "nindya", "nita", "novi", "novia", "novita", "nur", "nuraini", "nurhalimah", "nurhasanah",
    "nurhayati", "nuri", "nurjannah", "nurlaila", "nurul", "nyimas", "octavia", "okta",
    "olivia", "pertiwi", "prasasti", "priska", "puji", "purnama", "puspa", "puspita",
    "putri", "queen", "rachel", "rahayu", "rahma", "rahmadhani", "rahmawati", "rahmi",
    "raisa", "ramadhani", "ramona", "ratih", "ratna", "ratu", "regina", "renata", "reni",
    "resti", "retno", "rika", "rina", "rini", "risma", "rita", "riri", "riska", "rista",
    "riza", "rizka", "rosa", "rosita", "safira", "safitri", "sagita", "salma", "salsabila",
    "salwa", "sandra", "santi", "sari", "sarah", "seli", "septia", "septiani", "seruni",
    "shafira", "shanty", "sherly", "shinta", "silvia", "siska", "siti", "sonia", "sri",
    "sulastri", "susanti", "susi", "syafira", "syafitri", "syakira", "tamara", "tania",
    "tanti", "tarisa", "tasya", "tia", "tiara", "titi", "tri", "tuti", "ulfa", "ulfah",
    "umi", "utami", "vania", "vanya", "vera", "vina", "viona", "vivi", "wahyuni", "wati",
    "widya", "wiwik", "wulan", "wulandari", "yani", "yanti", "yayuk", "yeni", "yesi",
    "yeti", "yohana", "yolanda", "yuana", "yudith", "yulia", "yuliana", "yulianti", "yuni",
    "yunita", "yuyun", "zahra", "zahrani", "zaskia", "zulfa", "zaskiah",
}
MALE_SUFFIXES = ("syah", "wan", "man", "din", "yudi", "put", "putra")
FEMALE_SUFFIXES = ("wati", "ningsih", "sari", "lesti", "riana", "yanti", "ningtyas", "ulfa", "putri")
NEUTRAL = {"dwi", "eka", "tri", "nur", "cahya", "fitra", "rahayu", "wahyu", "agung", "bintang", "cahaya"}
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
        # Tidak cukup sinyal untuk memutuskan - confidence harus 0, bukan rasio sinyal
        # yang lemah itu sendiri (dulu bisa melaporkan confidence tinggi tanpa label).
        return GenderEstimate(None, 0.0)
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
