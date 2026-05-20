"""
Game Routes for HalluciNO

Manages quiz sessions in-memory: question selection by difficulty/category,
answer scoring with streaks, per-session review, and a global leaderboard.
"""

import random
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.data.questions import QUESTIONS

router = APIRouter()

# In-memory stores. Reset whenever the server restarts.
SESSIONS: Dict[str, Dict[str, Any]] = {}
LEADERBOARD: List[Dict[str, Any]] = []


class AnswerRequest(BaseModel):
    question_id: int
    user_answer: bool  # True = "Hallucination", False = "Truth"
    time_taken: int = 0


FEEDBACK_CORRECT = [
    "🎯 Nailed it!",
    "🧠 Smart move!",
    "✨ AI radar on point!",
    "🚀 You spotted that one!",
    "💯 Spot on!",
]

FEEDBACK_WRONG = [
    "🤖 The AI fooled you!",
    "😅 So close — try the next one!",
    "🌀 Tricky one, huh?",
    "🎭 The hallucination got you!",
    "🧩 Don't worry, learn and continue!",
]

STREAK_MILESTONES = {
    2: "🔥 2x Streak!",
    3: "🔥🔥 3x Streak!",
    5: "💥 5x Streak — On Fire!",
    7: "⚡ 7x Streak — Unstoppable!",
    10: "🏆 10x Streak — Legendary!",
}


def get_badge(accuracy: float) -> str:
    if accuracy >= 90:
        return "🏆 AI Master"
    if accuracy >= 80:
        return "🥇 Hallucination Detective"
    if accuracy >= 70:
        return "🥈 AI Spotter"
    if accuracy >= 60:
        return "🥉 Beginner Skeptic"
    return "🤖 AI Fell for It"


def all_categories() -> List[str]:
    return sorted({q.category for q in QUESTIONS})


@router.get("/categories")
async def get_categories():
    """Return the list of all question categories."""
    return {"categories": all_categories(), "total": len(QUESTIONS)}


@router.post("/start/{user_id}")
async def start_game(
    user_id: str,
    difficulty: str = "beginner",
    question_count: int = 10,
    username: str = "",
    category: Optional[str] = None,
):
    """Create a new session: pick questions by difficulty (+optional category)."""
    pool = [q for q in QUESTIONS if q.difficulty.value == difficulty.lower()]
    if category and category.lower() != "all":
        pool = [q for q in pool if q.category == category]

    # Fallbacks if filter yields nothing
    if not pool and category and category.lower() != "all":
        pool = [q for q in QUESTIONS if q.difficulty.value == difficulty.lower()]
    if not pool:
        pool = list(QUESTIONS)

    random.shuffle(pool)
    chosen = pool[: max(1, question_count)]

    session_id = f"session_{user_id}_{random.randint(100000, 999999)}"
    SESSIONS[session_id] = {
        "session_id": session_id,
        "user_id": user_id,
        "username": username or user_id,
        "difficulty": difficulty,
        "category": category or "all",
        "questions": chosen,
        "current_index": 0,
        "score": 0,
        "streak": 0,
        "max_streak": 0,
        "correct_answers": 0,
        "answers": [],
        "category_breakdown": {},
    }

    return {
        "session_id": session_id,
        "user_id": user_id,
        "username": username,
        "difficulty": difficulty,
        "category": category or "all",
        "total_questions": len(chosen),
    }


@router.get("/question/{session_id}")
async def get_question(session_id: str):
    """Return the current question for the session."""
    s = SESSIONS.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    if s["current_index"] >= len(s["questions"]):
        return {
            "game_completed": True,
            "message": "All questions completed",
            "total_questions": len(s["questions"]),
        }

    q = s["questions"][s["current_index"]]
    return {
        "question_id": q.id,
        "question": q.question,
        "category": q.category,
        "difficulty": q.difficulty.value,
        "hints": q.hints or [],
        "question_number": s["current_index"] + 1,
        "total_questions": len(s["questions"]),
    }


@router.post("/submit-answer/{session_id}")
async def submit_answer(session_id: str, request: AnswerRequest):
    """Grade an answer, update session state, return feedback + score delta."""
    s = SESSIONS.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if s["current_index"] >= len(s["questions"]):
        raise HTTPException(status_code=400, detail="Game already completed")

    q = s["questions"][s["current_index"]]
    is_correct = (request.user_answer == q.is_hallucination)

    points_change = 0
    streak_message = ""

    if is_correct:
        points_change += 10
        s["streak"] += 1
        s["max_streak"] = max(s["max_streak"], s["streak"])
        s["correct_answers"] += 1
        feedback = random.choice(FEEDBACK_CORRECT)
        if s["streak"] in STREAK_MILESTONES:
            points_change += 2
            streak_message = STREAK_MILESTONES[s["streak"]]
        s["category_breakdown"][q.category] = s["category_breakdown"].get(q.category, 0) + 10
    else:
        points_change -= 3
        s["streak"] = 0
        feedback = random.choice(FEEDBACK_WRONG)

    s["score"] = max(0, s["score"] + points_change)

    s["answers"].append({
        "question_id": q.id,
        "category": q.category,
        "question": q.question,
        "user_answer": "Hallucination" if request.user_answer else "Truth",
        "correct_answer": "Hallucination" if q.is_hallucination else "Truth",
        "is_correct": is_correct,
        "explanation": q.explanation,
        "time_taken": request.time_taken,
    })

    s["current_index"] += 1
    game_completed = s["current_index"] >= len(s["questions"])

    # Confidence meter for the just-answered question (95% if it really is a
    # hallucination, 5% otherwise — a deterministic post-hoc reveal).
    hallucination_probability = 95 if q.is_hallucination else 5

    return {
        "is_correct": is_correct,
        "feedback": feedback,
        "explanation": q.explanation,
        "correct_answer": "Hallucination" if q.is_hallucination else "Truth",
        "current_score": s["score"],
        "streak": s["streak"],
        "max_streak": s["max_streak"],
        "points_change": points_change,
        "streak_message": streak_message,
        "hallucination_probability": hallucination_probability,
        "game_completed": game_completed,
    }


@router.get("/final-score/{session_id}")
async def get_final_score(session_id: str):
    """Compute final stats, award achievements, and post to the leaderboard."""
    s = SESSIONS.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    total = len(s["questions"])
    correct = s["correct_answers"]
    accuracy = round((correct / total) * 100, 1) if total else 0.0
    badge = get_badge(accuracy)

    achievements = []
    if total > 0 and correct == total:
        achievements.append({
            "icon": "💎",
            "name": "Perfectionist",
            "description": "Got every question right!",
        })
    if s["max_streak"] >= 5:
        achievements.append({
            "icon": "🔥",
            "name": "Streak Master",
            "description": f"Max streak of {s['max_streak']}!",
        })
    if accuracy >= 80:
        achievements.append({
            "icon": "🎓",
            "name": "AI Scholar",
            "description": "Scored 80%+ accuracy",
        })
    if s["score"] >= 100:
        achievements.append({
            "icon": "💯",
            "name": "Centurion",
            "description": "Reached 100+ points",
        })

    achievement_message = (
        "Amazing performance! Keep it up!" if achievements
        else "Play more to earn badges!"
    )

    # Upsert leaderboard entry for this session.
    entry = {
        "session_id": session_id,
        "username": s["username"],
        "score": s["score"],
        "accuracy": accuracy,
        "max_streak": s["max_streak"],
        "badge": badge,
    }
    LEADERBOARD[:] = [e for e in LEADERBOARD if e["session_id"] != session_id]
    LEADERBOARD.append(entry)
    LEADERBOARD.sort(key=lambda e: e["score"], reverse=True)

    return {
        "session_id": session_id,
        "username": s["username"],
        "final_score": s["score"],
        "total_questions": total,
        "correct_answers": correct,
        "max_streak": s["max_streak"],
        "accuracy_percentage": accuracy,
        "badge": badge,
        "category_breakdown": s["category_breakdown"],
        "question_review": s["answers"],
        "achievements": achievements,
        "achievement_message": achievement_message,
    }


@router.get("/leaderboard")
async def get_leaderboard(limit: int = 10):
    """Top N completed sessions, ranked by score."""
    top = LEADERBOARD[: max(1, limit)]
    ranked = [{"rank": i + 1, **e} for i, e in enumerate(top)]
    return {"leaderboard": ranked, "total_players": len(LEADERBOARD)}


@router.post("/restart/{session_id}")
async def restart_game(session_id: str):
    """Drop a session so the user can start fresh."""
    SESSIONS.pop(session_id, None)
    return {"message": "Session reset", "session_id": session_id}
