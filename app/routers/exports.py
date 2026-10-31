from typing import Optional

from fastapi import APIRouter, Query

from app.utils import make_csv_response

router = APIRouter(tags=["exports"])


@router.get("/export/report1/csv")
async def export_report1_csv(
    state: Optional[str] = Query(None), district: Optional[str] = Query(None),
    township: Optional[str] = Query(None), village: Optional[str] = Query(None),
):
    demo = [
        ["ရန်ကုန်တိုင်းဒေသကြီး", "ခရိုင် ၁", "မြို့နယ် ၁", "ကျေးရွာအုပ်စု ၁", 45, 18, 17, 122, 24],
        ["ရန်ကုန်တိုင်းဒေသကြီး", "ခရိုင် ၁", "မြို့နယ် ၂", "ကျေးရွာအုပ်စု ၂", 32, 7, 10, 25, 10],
    ]

    def _m(r):
        if state and r[0] != state: return False
        if district and r[1] != district: return False
        if township and r[2] != township: return False
        if village and r[3] != village: return False
        return True

    filtered = [r for r in demo if _m(r)]
    rows = [
        [i, r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[5]+r[6]+r[7]+r[8]]
        for i, r in enumerate(filtered, 1)
    ]
    headers = ["စဉ်", "တိုင်း/ပြည်နယ်", "ခရိုင်", "မြို့နယ်", "ကျေးရွာအုပ်စု",
               "အိမ်ထောင်စု", "တိရိစ္ဆာန်ကြီး", "တိရိစ္ဆာန်ငယ်",
               "ကြက်/ဘဲ/ငုံး", "မျိုးတိရိစ္ဆာန်", "စုစုပေါင်း"]
    return make_csv_response(rows, headers, "report1_နယ်မြေဒေသအလိုက်")


@router.get("/export/report2/csv")
async def export_report2_csv(group: Optional[str] = Query(None),
                             state: Optional[str] = Query(None)):
    demo = [["large", "တိရိစ္ဆာန်ကြီး", "နွား", "ဒေသရင်း", 12, 25, 8, 45]]
    filtered = [r for r in demo if (not group or group == "all" or r[0] == group)]
    rows = [
        [i, r[1], r[2], r[3], r[4], r[5], r[6], r[7]]
        for i, r in enumerate(filtered, 1)
    ]
    headers = ["စဉ်", "အုပ်စု", "တိရိစ္ဆာန်အမျိုးအစား", "မျိုး (Breed)",
               "အထီး", "အမ", "သင်းကွပ်", "စုစုပေါင်း"]
    return make_csv_response(rows, headers, "report2_တိရိစ္ဆာန်အမျိုးအစားအလိုက်")