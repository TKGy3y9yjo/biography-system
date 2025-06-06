from __future__ import annotations
from openai import OpenAI
import config
import re
import random
from typing import List, Dict
from functools import lru_cache
import difflib
import json

# ========= 輔助函式（若專案已有同名工具，可刪除此處） =========
CLIENT = OpenAI(api_key=config.OPENAI_API_KEY)

@lru_cache(maxsize=64)
def _llm_score(text: str) -> tuple[float, float, float]:
    """
    呼叫 GPT，回傳 detail / emotion / reflection 三分數 0~1
    加 lru_cache，可避免同段文字重算
    """
    prompt = (
        "你是一位寫作老師，請以 0-1 分評估以下文字的："
        "detail(具體程度)、emotion(情感豐富度)、reflection(自省/價值觀)。\n"
        f"文字：'''{text}'''\n"
        "請只回 JSON，如：{\"detail\":0.8,\"emotion\":0.6,\"reflection\":0.5}"
    )
    try:
        rsp = CLIENT.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "請嚴格依格式回傳"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=50,
            temperature=0,
        )
        data = json.loads(rsp.choices[0].message.content.strip())
        return float(data.get("detail", 0)), float(data.get("emotion", 0)), float(
            data.get("reflection", 0)
        )
    except Exception:
        # 若 LLM 失敗，給中間分數避免中斷
        return 0.5, 0.5, 0.5


# ========= ② 重複度計算 =========
def _redundancy(curr: str, history: list[str]) -> float:
    if not history:
        return 0.0
    last = history[-1]
    return difflib.SequenceMatcher(None, curr, last).ratio()


# ========= ③ 公開 evaluate_answer =========
def evaluate_answer(answer: str, history: list[str]) -> dict:
    """
    回傳：
        {
          detail_score, emotion_score, reflection_score,
          redundancy, length, aqi
        }
    """
    d, e, r = _llm_score(answer)
    red = _redundancy(answer, history)
    length = len(answer)
    return {
        "detail_score": d,
        "emotion_score": e,
        "reflection_score": r,
        "redundancy": red,
        "length": length,
        "aqi": (d + e + r) / 3,
    }
EMOTION_WORDS = {
    "正面": ["開心", "喜悅", "興奮", "快樂", "自豪"],
    "負面": ["難過", "失落", "憤怒", "挫折", "害怕"],
}

def extract_key_element(text: str) -> str:
    """簡易抓取第一個可能的人物／地點／事件名詞"""
    match = re.search(r"[A-Za-z\u4e00-\u9fff]{2,}", text)
    return match.group(0) if match else "這段經歷"

def analyze_emotion(text: str) -> str:
    """非常粗略的情感偵測：出現關鍵詞就標記"""
    for tone, words in EMOTION_WORDS.items():
        if any(w in text for w in words):
            return "積極" if tone == "正面" else "消極"
    return "中性"

def summarize_history(history: List[str], max_len: int = 100) -> str:
    """將過往回答串起來（限長度）"""
    if not history:
        return "（無）"
    joined = " ｜ ".join(history)
    return (joined[:max_len] + "…") if len(joined) > max_len else joined

# ========= 使用者提供的核心邏輯 =========

def generate_follow_up_question(user_answer, current_theme, question_history, story_context):
    """
    生成更智能的追問問題
    --------------------------------------------------
    依照使用者原始程式碼改寫為繁體中文版本。
    """

    # 1. 分析回答內容的關鍵資訊
    def analyze_answer_content(answer):
        """分析回答中的關鍵元素"""
        analysis_prompt = f"""
        請分析以下回答，提取關鍵資訊：
        回答："{answer}"
        
        請識別：
        1. 具體的人物、地點、時間
        2. 情感色彩（積極/消極/中性）
        3. 未展開的細節
        4. 可深入挖掘的方向
        
        以 JSON 格式返回：
        {{
            "key_elements": ["人物1", "地點1", "事件1"],
            "emotion_tone": "積極/消極/中性",
            "unexplored_details": ["細節1", "細節2"],
            "digging_directions": ["方向1", "方向2"]
        }}
        """
        return analysis_prompt

    # 2. 多層次追問策略
    follow_up_strategies: Dict[str, Dict[str, str]] = {
        "detail_expansion": {
            "description": "細節擴充型追問",
            "prompt_template": """
            基於回答："{answer}"
            
            使用者提到了 {key_element}，請生成一個追問，讓使用者：
            1. 描述更具體的場景細節
            2. 回憶當時的感受與想法
            3. 說明此事的影響或意義
            
            問題需：
            - 具體而不抽象
            - 引導情感表達
            - 避免簡單的是非題
            - 字數控制在 20–40 字
            
            生成問題：
            """
        },
        "emotional_depth": {
            "description": "情感深度挖掘",
            "prompt_template": """
            使用者回答："{answer}"
            主題：{theme}
            
            此回答展現出 {emotion_tone} 的情感傾向。
            請生成一個問題，協助使用者：
            1. 表達更深層的情感體驗
            2. 探索此經歷的情感影響
            3. 連結過去與現在的感受
            
            問題示例風格：
            -「那時候的你內心是什麼感受？」
            -「這件事對你後來有什麼影響？」
            -「回想起來，你會對當時的自己說什麼？」
            
            生成追問：
            """
        },
        "context_connection": {
            "description": "上下文關聯型",
            "prompt_template": """
            當前回答："{answer}"
            主題：{theme}
            先前回答歷史：{history_summary}
            
            請生成一個問題，將這次回答與：
            1. 同主題的其他經歷連結
            2. 不同主題間的關聯
            3. 時間線上的前後關係
            
            問題應能引導：
            - 模式與規律
            - 成長變化
            - 影響關係
            
            生成問題：
            """
        },
        "story_completion": {
            "description": "故事完整性補充",
            "prompt_template": """
            使用者回答："{answer}"
            
            此回答中的故事似乎尚未說完。
            請生成問題協助使用者：
            1. 補充故事的開端／過程／結果
            2. 說明重要轉折點
            3. 描述關鍵人物的作用
            
            問題需：
            - 自然承接使用者敘述
            - 鼓勵故事性表達
            - 避免過於直接的詢問
            
            生成問題：
            """
        }
    }

    # 3. 智能策略選擇
    def choose_strategy(answer, theme, question_count):
        """依情況選擇最合適的追問策略"""
        answer_length = len(answer)
        if answer_length < 50:
            return "detail_expansion"
        elif any(word in answer for word in ("感覺", "覺得")):
            return "emotional_depth"
        elif question_count > 2:
            return "context_connection"
        else:
            return "story_completion"

    # 4. 問題品質檢查
    def validate_question(question):
        """檢查生成問題的品質"""
        quality_checklist = {
            "length_appropriate": 15 <= len(question) <= 50,
            "not_yes_no": not any(w in question for w in ("是不是", "有沒有", "會不會")),
            "encourages_narrative": any(w in question for w in ("怎麼", "什麼", "為什麼", "如何")),
            "emotionally_engaging": any(w in question for w in ("感受", "想法", "心情", "覺得"))
        }
        score = sum(quality_checklist.values())
        return score >= 3, quality_checklist

    # 5. 備用問題庫
    def generate_fallback_question(theme, answer):
        """當 AI 生成的問題品質不佳時使用"""
        fallback_questions = {
            "童年": [
                "能再詳細描述一下當時的場景嗎？",
                "那時你的心情如何？",
                "這件事對你有什麼特別意義？"
            ],
            "教育": [
                "這段學習經歷如何影響了你？",
                "你從中學到了什麼重要收穫？",
                "有沒有特別印象深刻的老師或同學？"
            ],
            "職業": [
                "工作中最有成就感的時刻是什麼？",
                "遇過哪些重大的職涯轉折？",
                "這份工作帶給你什麼人生啟發？"
            ],
        }
        return random.choice(fallback_questions.get(theme, ["可以再多說一些嗎？"]))

    # 6. 主要追問生成函式
    def generate_smart_follow_up(answer, theme, history):
        strategy = choose_strategy(answer, theme, len(history))
        prompt_data = {
            "answer": answer,
            "theme": theme,
            "key_element": extract_key_element(answer),
            "emotion_tone": analyze_emotion(answer),
            "history_summary": summarize_history(history)
        }
        full_prompt = follow_up_strategies[strategy]["prompt_template"].format(**prompt_data)

        client = OpenAI(api_key=config.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "你是一位專業的傳記作家與心理訪談師，擅長透過精巧提問引導人們分享深層人生故事。"
                },
                {"role": "user", "content": full_prompt}
            ],
            max_tokens=150,
            temperature=0.8
        )
        question = response.choices[0].message.content.strip()
        is_valid, _ = validate_question(question)
        if not is_valid:
            question = generate_fallback_question(theme, answer)
        return question

    # 封裝成閉包供外部調用
    def _inner(answer, theme, history):
        return generate_smart_follow_up(answer, theme, history)

    return _inner  # 返回可直接呼叫的函式

# ========= 對外 API =========

def get_next_question(answer: str, theme: str, history: List[str]) -> str:
    """
    對 routes 呼叫的單一入口
    --------------------------------------------------
    用法：
        next_q = get_next_question(answer, current_theme, history_texts)
    """
    generator = generate_follow_up_question(answer, theme, history, {})
    return generator(answer, theme, history)
