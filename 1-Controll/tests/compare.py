import json, sys, difflib, re
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
ok = True
missing = sorted(set(a.get("surface", [])) - set(b.get("surface", [])))
print("metodi/attributi pubblici mancanti:", missing or "nessuno")
ok &= not missing
IGN = {"absolute_import", "math", "socket", "threading", "time", "j", "clamp", "fake_robot_enabled",
       "get_wav_bytes_from_pepper", "http_get_json", "normalize_gesture_id", "record_wav_on_pepper",
       "safe_unicode", "string_types", "tcp_check", "webapp_upload_audio"}
mm = sorted(set(a.get("module", [])) - set(b.get("module", [])) - IGN)
print("nomi del modulo mancanti:", mm or "nessuno"); ok &= not mm
if "results" in a:
    diffs = [(x, y) for x, y in zip(a["results"], b["results"]) if x != y]
    print("risultati diversi: %d su %d" % (len(diffs), len(a["results"])))
    for x, y in diffs: print("  PRIMA", x, "\n  DOPO ", y)
    ok &= not diffs and len(a["results"]) == len(b["results"])
for key in ("status", "saved", "frames", "title"):
    if key in a:
        same = a[key] == b[key]; print("%s uguale: %s" % (key, same)); ok &= same
def strip(lines):
    return [re.sub(r"/tmp/\S+", "<tmp>", l) for l in lines]
la, lb = strip(a["log"]), strip(b["log"])
same_multiset = sorted(la) == sorted(lb)
d = [l for l in difflib.unified_diff(la, lb, lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
print("log: %d righe prima, %d dopo; stesse righe (ordine dei thread a parte): %s" % (len(la), len(lb), same_multiset))
if not same_multiset:
    from collections import Counter
    ca, cb = Counter(la), Counter(lb)
    print("  solo prima:", list((ca - cb).items())[:15]); print("  solo dopo:", list((cb - ca).items())[:15])
ok &= same_multiset
print("ESITO:", "IDENTICO" if ok else "DIFFERENZE")
