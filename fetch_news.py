# يجيب الأخبار من مواقع الأخبار (RSS) ويحفظها في news.json
import json, re, html, time, os, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

UA = "Mozilla/5.0 (compatible; OmarNewsBot/1.0)"
FEEDS = {
    "ar": [
        ("BBC عربي", "https://feeds.bbci.co.uk/arabic/rss.xml", None),
        ("DW عربية", "https://rss.dw.com/xml/rss-ar-all", None),
        ("فرانس 24", "https://www.france24.com/ar/rss", None),
        ("سكاي نيوز عربية", "https://www.skynewsarabia.com/rss", None),
        ("الجزيرة", "https://www.aljazeera.net/rss", None),
    ],
    "en": [
        ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "world"),
        ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml", "business"),
        ("BBC Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml", "tech"),
        ("BBC Sport", "https://feeds.bbci.co.uk/sport/rss.xml", "sport"),
        ("The Guardian", "https://www.theguardian.com/world/rss", None),
    ],
}
PER_FEED = 25
MAX_TOTAL = 90

KW = [
    ("egypt", r"مصر|المصري|المصرية|القاهرة|السيسي|الإسكندرية|\bEgypt|Egyptian|\bCairo"),
    ("sport", r"رياضة|الرياضي|كرة|مباراة|الدوري|كأس|لاعب|هدف|أولمبي|بطولة|\bfootball|\bmatch\b|league|Premier|cricket|tennis|Olympic"),
    ("business", r"اقتصاد|أسعار|الدولار|بنك|بورصة|نفط|تضخم|أسهم|استثمار|الذهب|تجارة|\bmarket|economy|inflation|\bbank|oil price|stocks|tariff|trade"),
    ("tech", r"تكنولوجيا|ذكاء اصطناعي|تطبيق|هاتف|آبل|غوغل|مايكروسوفت|إنترنت|سيبراني|روبوت|ناسا|الفضاء|\bAI\b|\btech|Apple|Google|Microsoft|cyber|robot|NASA|software"),
    ("culture", r"فيلم|مهرجان|ثقافة|كتاب|معرض|موسيقى|سينما|مسلسل|أدب|متحف|فنان|\bfilm|music|museum|festival|book|art\b|artist|cinema"),
]

def local(tag):
    return tag.rsplit("}", 1)[-1]

def clean(s, n):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > n:
        s = s[:n].rsplit(" ", 1)[0] + "…"
    return s

def classify(text, forced):
    if forced:
        return forced
    for cat, rx in KW:
        if re.search(rx, text, re.I):
            return cat
    return "world"

def best_image(item):
    best, bw = "", -1
    for el in item.iter():
        n = local(el.tag)
        if n in ("thumbnail", "content", "enclosure"):
            u = el.attrib.get("url", "")
            t = el.attrib.get("type", "") + el.attrib.get("medium", "")
            if not u.startswith("http"):
                continue
            if n != "thumbnail" and t and "image" not in t:
                continue
            if n == "content" and not t and not re.search(r"\.(jpe?g|png|webp)", u, re.I):
                continue
            try:
                w = int(el.attrib.get("width", "0"))
            except ValueError:
                w = 0
            if w >= bw:
                best, bw = u, w
    if not best:
        raw = ET.tostring(item, encoding="unicode")
        m = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)', html.unescape(raw))
        if m:
            best = m.group(1)
    best = re.sub(r"(ichef\.bbci\.co\.uk/[^ ]*?/)(?:240|320|480)/", r"\g<1>660/", best)
    return best

def parse_date(s):
    try:
        d = parsedate_to_datetime(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)

def fetch(name, url, forced):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    data = urllib.request.urlopen(req, timeout=25).read()
    root = ET.fromstring(data)
    out = []
    for item in root.iter("item"):
        f = {local(c.tag): (c.text or "") for c in item}
        title = clean(f.get("title"), 200)
        link = (f.get("link") or "").strip()
        if not title or not link.startswith("http"):
            continue
        desc = clean(f.get("description") or f.get("encoded"), 400)
        if desc.startswith(title[:40]):
            desc = ""
        out.append({
            "t": title, "d": desc, "l": link, "s": name,
            "i": best_image(item), "c": classify(title + " " + desc, forced),
            "p": parse_date(f.get("pubDate") or f.get("date") or "").isoformat(),
        })
        if len(out) >= PER_FEED:
            break
    return out

if os.environ.get("ONLY") or os.environ.get("ENRICH_ONLY"):
    FEEDS = {"ar": [], "en": []}
try:
    old = json.load(open("news.json", encoding="utf-8"))
except Exception:
    old = {}

result = {"updated": datetime.now(timezone.utc).isoformat()}
for lang, feeds in FEEDS.items():
    items, ok = [], 0
    for name, url, forced in feeds:
        got = None
        for attempt in range(2):
            try:
                got = fetch(name, url, forced)
                break
            except Exception as e:
                print("فشل", name, e)
                time.sleep(3)
        if got:
            ok += 1
            items += got
        else:
            items += [x for x in old.get(lang, []) if x.get("s") == name]
    seen, uniq = set(), []
    for x in sorted(items, key=lambda x: x["p"], reverse=True):
        if x["l"] in seen:
            continue
        seen.add(x["l"])
        uniq.append(x)
    result[lang] = uniq[:MAX_TOTAL]
    print(lang, "مصادر شغالة:", ok, "/", len(feeds), "أخبار:", len(result[lang]))

if not (os.environ.get("ONLY") or os.environ.get("ENRICH_ONLY")):
    with open("news.json", "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, separators=(",", ":"))


# ---------- أخبار الدول (من Google News RSS) ----------
COUNTRIES = [
 ("EG","مصر","Egypt"),("SA","السعودية","Saudi Arabia"),("AE","الإمارات","United Arab Emirates"),
 ("KW","الكويت","Kuwait"),("QA","قطر","Qatar"),("BH","البحرين","Bahrain"),("OM","عمان","Oman"),
 ("IQ","العراق","Iraq"),("JO","الأردن","Jordan"),("LB","لبنان","Lebanon"),("SY","سوريا","Syria"),
 ("PS","فلسطين","Palestine"),("YE","اليمن","Yemen"),("SD","السودان","Sudan"),("LY","ليبيا","Libya"),
 ("TN","تونس","Tunisia"),("DZ","الجزائر","Algeria"),("MA","المغرب","Morocco"),
 ("US","أمريكا","United States"),("GB","بريطانيا","United Kingdom"),("FR","فرنسا","France"),
 ("DE","ألمانيا","Germany"),("TR","تركيا","Turkey"),("ES","إسبانيا","Spain"),("IT","إيطاليا","Italy"),
 ("RU","روسيا","Russia"),("IN","الهند","India"),("CN","الصين","China"),("JP","اليابان","Japan"),
 ("BR","البرازيل","Brazil"),("CA","كندا","Canada"),("AU","أستراليا","Australia"),
 ("NG","نيجيريا","Nigeria"),("ZA","جنوب أفريقيا","South Africa"),
]

def gn_get(url):
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(req, timeout=25).read()
        except Exception as e:
            print("   إعادة", e)
            time.sleep(15 if "429" in str(e) else 4)
    return None

def gn_items(query, hl, gl):
    q = urllib.parse.quote(query + " when:2d")
    url = "https://news.google.com/rss/search?q=%s&hl=%s&gl=%s&ceid=%s:%s" % (q, hl, gl, gl, hl)
    data = gn_get(url)
    if not data:
        return None
    root = ET.fromstring(data)
    out = []
    for item in root.iter("item"):
        f = {local(c.tag): (c.text or "") for c in item}
        src = ""
        for c in item:
            if local(c.tag) == "source":
                src = (c.text or "").strip()
        title = clean(f.get("title"), 300)
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3].strip()
        link = (f.get("link") or "").strip()
        if not title or not link.startswith("http"):
            continue
        rel = []
        for m in re.finditer(r"<li>\s*<a[^>]*>(.*?)</a>", html.unescape(f.get("description", "")), re.S):
            r = clean(m.group(1), 200)
            r = re.sub(r"\s-\s[^-]{2,40}$", "", r)
            if r and r != title and r not in rel:
                rel.append(r)
        d = ""
        for r in rel:
            if len(d) + len(r) > 400:
                break
            d += (" • " if d else "") + r
        out.append({"t": title, "d": d, "l": link, "s": src or "Google News", "i": "",
                    "c": classify(title + " " + d, None),
                    "p": parse_date(f.get("pubDate") or "").isoformat()})
    return out

def enrich(items):
    """يضيف تحت كل خبر عناوين أخبار قريبة منه من مصادر تانية (لأن Google News مش بيدي ملخص)"""
    def words(t):
        return set(w for w in re.findall(r"\w+", t.lower()) if len(w) > 3)
    ws = [words(x["t"]) for x in items]
    for i, x in enumerate(items):
        if x["d"] or not ws[i]:
            continue
        sc = []
        for j, y in enumerate(items):
            if i == j or y["s"] == x["s"] or not ws[j]:
                continue
            k = len(ws[i] & ws[j]) / float(min(len(ws[i]), len(ws[j])))
            if k >= 0.4:
                sc.append((k, y))
        d = ""
        for k, y in sorted(sc, key=lambda a: -a[0])[:3]:
            if len(d) + len(y["t"]) > 400:
                break
            d += (" • " if d else "") + y["t"] + " (" + y["s"] + ")"
        x["d"] = d

os.makedirs("c", exist_ok=True)
if os.environ.get("ENRICH_ONLY"):
    import glob
    for p in glob.glob("c/*.json"):
        d = json.load(open(p, encoding="utf-8"))
        for l in ("ar", "en"):
            enrich(d[l])
        json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    raise SystemExit
for cc, ar, en in COUNTRIES:
    if os.environ.get("ONLY") and cc not in os.environ["ONLY"].split(","):
        continue
    path = "c/%s.json" % cc
    try:
        oldc = json.load(open(path, encoding="utf-8"))
    except Exception:
        oldc = {}
    res = {"updated": datetime.now(timezone.utc).isoformat()}
    for lang, q, hl, gl in (("ar", ar, "ar", "EG"), ("en", en, "en", "US")):
        got = gn_items(q, hl, gl)
        time.sleep(3)
        if got:
            seen, uniq = set(), []
            for x in sorted(got, key=lambda x: x["p"], reverse=True):
                if x["t"] in seen:
                    continue
                seen.add(x["t"])
                uniq.append(x)
            enrich(uniq)
            res[lang] = uniq[:60]
        else:
            res[lang] = oldc.get(lang, [])
    print(cc, len(res["ar"]), len(res["en"]))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, separators=(",", ":"))

# يضيف ملفات الدول للحفظ (الـ workflow القديم بيعمل commit للي اتضاف)
import subprocess
if not os.environ.get("ONLY") and os.path.isdir(".git"):
    subprocess.run(["git", "add", "-A", "c"])
