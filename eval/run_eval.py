"""Accuracy evaluation of both sections against the live AI.
   python eval/run_eval.py            (sample dashboard must run on :9000)
   python eval/run_eval.py --speech   voice -> noise -> speech-to-text -> agent
Prints a score per language and writes eval/report.json."""
import argparse, json, os, re, subprocess, sys, tempfile, time
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT); os.chdir(ROOT)
os.environ["DATA_DIR"] = tempfile.mkdtemp()
import yaml
from concurrent.futures import ThreadPoolExecutor
from app import db
from app.ai import speech
from app.ai.agent import Agent
from app.ai.languages import detect_script_language, foreign_script
from app.ai.llm import LLM
from app.connect import core as connect
from app.service_center import core as service

JUDGE = LLM(order=["nvidia", "sarvam"], timeout=40)


def judge(rubric, q, a):
    m = JUDGE.chat([{"role": "system", "content": "Grade a phone assistant's reply strictly but fairly. JSON only: {\"pass\": true/false, \"reason\": \"short\"}"},
                    {"role": "user", "content": f"Rubric: {rubric}\nCaller said: {q}\nAssistant replied: {a}"}], temperature=0, max_tokens=200)
    try:
        return json.loads(re.search(r"\{.*\}", m.get("content") or "", re.S).group(0))
    except Exception:
        return {"pass": False, "reason": "judge unreadable"}


def noisy(wav):
    return subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-f", "lavfi", "-i", "anoisesrc=color=pink:amplitude=0.07",
                           "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first", "-c:a", "libopus", "-f", "webm", "pipe:1"],
                          input=wav, capture_output=True, check=True).stdout


def run(case, key, use_speech):
    q, lang = case["q"][key], key.split("-")[0]
    if case["section"] == "service":
        agent = Agent(service.persona(), service.tools(case["caller"]), case["caller"], turn_rules=service.turn_rules(),
                      expose_caller=False)
    else:
        tools, _ = connect.tools(case["caller"])
        agent = Agent(connect.persona() + "\n" + connect.prefetch(case["caller"], {t.name: t for t in tools}), tools, case["caller"],
                      turn_rules=connect.turn_rules())
    r = {"id": case["id"], "lang": key, "q": q, "checks": {}}
    t = time.time()
    try:
        if use_speech:
            h = speech.transcribe_smart(noisy(speech.speak(q, lang)), lang)
            r["heard"], text = h["text"], h["text"]
        else:
            text = q
        a = agent.reply(text, lang)
    except Exception as e:
        return {**r, "reply": f"ERROR {e}", "passed": False, "sec": round(time.time() - t, 1)}
    r.update(reply=a, sec=round(time.time() - t, 1))
    c = r["checks"]
    c["language"] = (lang == "en" or key.endswith("mix") or detect_script_language(a, lang) == lang) and not foreign_script(a, lang)
    c["short"] = len(a.split()) <= 45
    if case.get("expect_tool"):
        c["checked_data"] = case["expect_tool"] in [x["tool"] for x in agent.actions]
    if case.get("must_not"):
        c["no_leak"] = not any(w.lower() in a.lower() for w in case["must_not"])
    try:
        j = judge(case["judge"], text, a)
    except Exception as e:
        j = {"pass": False, "reason": f"judge error {e}"}
    c["judge"], r["why"] = bool(j.get("pass")), j.get("reason")
    r["passed"] = all(c.values())
    return r


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--speech", action="store_true"); ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    db.init(); service.seed()
    assert connect.discover(os.environ.get("DASHBOARD", "http://127.0.0.1:9000"), "demo-key-123")["ok"], "start the sample dashboard"
    connect.seed_demo_rules()          # exactly what the app does for the sample dashboard
    cases = yaml.safe_load(open("eval/dataset.yaml", encoding="utf-8"))["cases"]
    jobs = [(c, k) for c in cases for k in c["q"]]
    with ThreadPoolExecutor(a.workers) as ex:
        res = list(ex.map(lambda j: run(j[0], j[1], a.speech), jobs))
    by = {}
    for r in res:
        by.setdefault(r["lang"], []).append(r)
        if not r["passed"]:
            print(f"FAIL {r['id']:16} {r['lang']:7} {[k for k, v in r['checks'].items() if not v]}\n   Q: {r.get('heard', r['q'])}\n   A: {r['reply']}\n   why: {r.get('why')}")
    print("\nlanguage  passed  avg time")
    for k, rs in by.items():
        print(f"{k:8} {sum(x['passed'] for x in rs):3}/{len(rs):<3}  {sum(x['sec'] for x in rs) / len(rs):.1f}s")
    tot = sum(x["passed"] for x in res)
    print(f"TOTAL    {tot}/{len(res)} = {100 * tot / len(res):.0f}%  ({'speech+noise' if a.speech else 'text'})")
    json.dump(res, open(f"eval/report{'_speech' if a.speech else ''}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
