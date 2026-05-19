import os
import json
import random
import requests
import time

API_KEY = "sk-Pmis7gCC2ZiQqf7B3jUHGnKVq0rM2z1VvUGxaLBJibijMezv"
API_URL = "https://apicz.boyuerichdata.com/v1/completions"
GEN_MODELS = ["gpt-4o"]          # 可以改为多模型轮换，当前效率选1个为例
REVIEW_MODELS = ["gpt-5.1-codex"]  # 评准模型，只评价准确性，量大建议1个
SAMPLE_NUM = 2000
MAX_LEN = 1200
# 路径修正为相对当前目录（假设在Summer-Camp-Projects目录下执行）
FILINGS_ROOT = "dataset/corpus/filings"
OUTPUT_FILE = "output/2000_summaries_with_accuracy_review.jsonl"

def extract_plaintext_from_html(filepath, max_len=MAX_LEN):
    import re
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()
    text = re.sub("<.*?>", "", html)
    text = text.replace("\n", " ").strip()
    return text[:max_len]

def gen_prompt(financial_text, company, year):
    return (f"请用300字以内中文总结下述{company}于{year}的财报内容，要求简洁、突出主要财务和经营变化，且不得照抄原句：\n{financial_text}\n")

def review_prompt(summary, context):
    return f"请只从“准确性”一项对下方AI简报进行10分制评分与20字简评：\n原文片段：{context}\nAI简报：{summary}"

def call_api(prompt, model):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "prompt": prompt,
        "max_tokens": 300,
        "temperature": 0.7
    }
    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            if "choices" in data and data["choices"]:
                return data["choices"][0]["text"].strip()
            elif "data" in data and data["data"]:
                return data["data"][0].get("text", "")
        else:
            return f"API({model})调用失败:{resp.text}"
    except Exception as e:
        return f"API({model})调用异常:{e}"
    return ""

def collect_all_files():
    records = []
    for c in os.listdir(FILINGS_ROOT):
        subdir = os.path.join(FILINGS_ROOT, c)
        if not os.path.isdir(subdir):
            continue
        for fname in os.listdir(subdir):
            if fname.startswith('.'):
                continue
            fpath = os.path.join(subdir, fname)
            # year 粗抽取（增强可再扩展）
            year = fname.split("__")[1][:4] if "__" in fname else "2025"
            records.append(dict(company=c, year=year, filepath=fpath, filename=fname))
    return records

def main():
    all_records = collect_all_files()
    if len(all_records) < SAMPLE_NUM:
        print(f"实际可采样数{len(all_records)} < 2000，请补充数据或允许重复采样")
        sample_records = random.choices(all_records, k=SAMPLE_NUM)
    else:
        sample_records = random.sample(all_records, k=SAMPLE_NUM)
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as fout:
        for idx, record in enumerate(sample_records):
            context = extract_plaintext_from_html(record["filepath"], MAX_LEN)
            used_model = random.choice(GEN_MODELS)
            summary = call_api(gen_prompt(context, record["company"], record["year"]), used_model)
            review_results = []
            for review_model in REVIEW_MODELS:
                accuracy_review = call_api(review_prompt(summary, context), review_model)
                review_results.append({"model": review_model, "accuracy_review": accuracy_review})
            item = {
                "company": record["company"],
                "year": record["year"],
                "filename": record["filename"],
                "context": context,
                "used_gen_model": used_model,
                "summary": summary,
                "accuracy_reviews": review_results
            }
            fout.write(json.dumps(item, ensure_ascii=False) + "\n")
            fout.flush()
            print(f"[{idx+1}/{SAMPLE_NUM}] {record['company']} {record['year']} {record['filename']} done.")
            time.sleep(0.3)  # 限速防ban，可根据API性能调整

if __name__ == "__main__":
    main()