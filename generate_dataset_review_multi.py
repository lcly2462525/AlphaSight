import os
import random
import requests

API_KEY = "sk-Pmis7gCC2ZiQqf7B3jUHGnKVq0rM2z1VvUGxaLBJibijMezv"
API_URL = "https://apicz.boyuerichdata.com/v1/completions"
GEN_MODELS = ["gpt-4o", "gpt-5.1", "gpt-5-mini"]  # 用于 summary 生成
REVIEW_MODELS = ["gpt-5.1-codex", "gpt-4o"]        # 评测模型，支持多个
AGG_MODEL = "gpt-4o"                              # 汇总判定模型

def gen_prompt(financial_text, company, year):
    return (
        f"请使用企业年报节选，针对 {company} 在 {year} 年的财报内容，用300字以内中文进行总结（总结关键财务与业务变化，避免照搬）：\n\n"
        f"{financial_text}\n"
    )

def review_prompt(summary, context):
    return (f"请对下方AI撰写的简报进行准确性、全面性、简洁性、创新性等多维度评价（内容打分并文字点评）：\n原文片段：{context}\nAI简报：{summary}")

def agg_prompt_with_reviews(summary_dict, reviews_dict, context):
    desc = "对下述不同AI生成的企业年报总结及其评测结果，判定哪份简报最准确全面，分别存在哪些优缺点，评测意见是否客观公正，可否进一步提升review方案（如需，给新prompt建议）。"
    for m, s in summary_dict.items():
        desc += f"\n===模型【{m}】AI简报===\n{s}\n"
        rlist = reviews_dict.get(m, [])
        for rev_idx, r in enumerate(rlist):
            desc += f"  - 评测{rev_idx+1}：{r}\n"
    desc += f"\n原文片段：{context}\n"
    return desc

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

def extract_plaintext_from_html(filepath, max_len=1400):
    import re
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()
    text = re.sub("<.*?>", "", html)
    text = text.replace("\n", " ").strip()
    return text[:max_len]

def main():
    base_dir = "Summer-Camp-Projects/dataset/corpus/filings/AAPL"
    files = os.listdir(base_dir)
    sample_file = random.choice(files)
    company = "Apple Inc."
    year = "2025"
    path = os.path.join(base_dir, sample_file)
    context = extract_plaintext_from_html(path, max_len=1400)

    # 1. 多模型生成 summary
    summary_dict = {}
    for model in GEN_MODELS:
        prompt = gen_prompt(context, company, year)
        summary = call_api(prompt, model)
        summary_dict[model] = summary
        print(f"=== {model} summary ===\n{summary}")

    # 2. 每个summary多模型多次评测
    reviews_dict = {}
    for model, summary in summary_dict.items():
        reviews = []
        for review_model in REVIEW_MODELS:
            prompt = review_prompt(summary, context)
            review = call_api(prompt, review_model)
            reviews.append(f"{review_model}: {review}")
            print(f"== review {model} by {review_model} ==\n{review}\n")
        reviews_dict[model] = reviews

    # 3. 汇总所有summary及评测，喂更强模型统一判定哪份最好并理由
    agg_prompt = agg_prompt_with_reviews(summary_dict, reviews_dict, context)
    agg_summary = call_api(agg_prompt, AGG_MODEL)
    print("==== 综合综述和裁决 ====")
    print(agg_summary)

if __name__ == "__main__":
    main()