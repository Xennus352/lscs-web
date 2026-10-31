ANIMAL_TYPES = {
    "atID01": {"table": "largeanimals",  "label": "large"},
    "atID02": {"table": "younganimals",  "label": "small"},
    "atID03": {"table": "livestock",     "label": "poultry"},
    "atID04": {"table": "breedingstock", "label": "breeding"},
}

BREEDING_ANIMAL_MAP = {
    "bsID01": "ဒေသနွား", "bsID02": "ဒေသကျွဲ", "bsID03": "နို့စားကျွဲ",
    "bsID04": "ဝက်", "bsID05": "ဆိတ်", "bsID06": "သိုး",
}

AGE_TO_KEY = {
    "atID01": {"ageID03": "u1", "ageID02": "m1_3", "ageID01": "o3"},
    "atID02": {"ageID06": "u2m", "ageID05": "m2_6m", "ageID04": "o6m"},
}

AGE_KEY_MAP = {
    "atID01": {"ageID03": "u1", "ageID02": "y1_3", "ageID01": "o3"},
    "atID02": {"ageID06": "u2m", "ageID05": "m2_6m", "ageID04": "o6m"},
    "atID03": {
        "ageID07": "young", "ageID08": "medium", "ageID09": "adult",
        "ageID10": "young_medium", "ageID11": "adult",
        "ageID12": "young", "ageID13": "medium", "ageID14": "adult",
        "ageID15": "young", "ageID16": "medium", "ageID17": "adult",
    },
}

GENDER_KEY_MAP = {"g01": "male", "g02": "castrated", "g03": "female"}

ANIMAL_TYPE_NAMES = [
    {"id": "atID01", "name": "တိရိစ္ဆာန်ကြီး"},
    {"id": "atID02", "name": "တိရိစ္ဆာန်ငယ်"},
    {"id": "atID03", "name": "ကြက်/ဘဲ/ငုံး"},
    {"id": "atID04", "name": "မျိုးတိရိစ္ဆာန်"},
]

GENDERS         = [{"id": "g01", "name": "အထီး"}, {"id": "g02", "name": "သင်းကွပ်အထီး"}, {"id": "g03", "name": "အမ"}]
GENDERS_BREEDING = [{"id": "g01", "name": "အထီး"}, {"id": "g03", "name": "အမ"}]

EDITABLE_PERSON_FIELDS = {
    "WardName", "householdNo", "interviewDate", "name", "gender",
    "eduStatus", "phoneNo", "age", "headName", "headEduStatus",
    "headGender", "headPhoneNo", "headAge", "Interviewer", "interviewerPhoneNo",
}
EDITABLE_ANIMAL_FIELDS = {
    "animalTypeID", "animalID", "speciesID", "ageID", "genderID", "dataCount",
}