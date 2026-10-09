# Memory Evolution & Trust Model: From Fuzzy Memory to Verifiable Claims

## 🌐 The Core Problem (The 'Four Worlds' Dilemma)
**Date:** October 2026
**Context:** Using multiple AI agents (Claude Code, Gemini CLI, Antigravity, IDE Chat) on a single project.

**The Pain Point:** 
Each agent maintains its own isolated context. This creates a "memory silo" where the developer must constantly re-explain the project state to every tool. The goal is a shared, automatic memory that doesn't just delete old data (because "old is not always wrong") and handles conflicting information intelligently.

---

## ⚡ The Collision: Enter the "Baton" Philosophy
**Interaction:** LinkedIn exchange with Stanimir Tenev (Founder & Lead Architect).

**Stanimir's Viewpoint:**
- **Shift from Memory -> Claims:** Stop treating agent memory as a "summary of the past" and start treating it as a **Claims Register** (a ledger of facts).
- **Status over Timestamp:** Instead of trusting the newest information, trust the most **verified** information.
- **The Statuses:**
    - *Agent's Word:* A claim made by an agent (unverified).
    - *Checked:* A claim verified against a source (source of truth).
- **The Debt Model:** Unchecked claims that persist for too long (e.g., 30 days) are flagged as "technical debt."

---

## 💡 The Breakthrough: The "Separate Checker"
**Our Contribution:**
While Baton's approach was a leap forward, it had a "Trust Gap": the agent writing the claim also set the status. This is **self-certification** and is fundamentally untrustworthy.

**The Solution:**
The **Writer** and the **Checker** must be separate roles.
1. **The Worker Agent:** Writes a claim -> `Status: Unverified`.
2. **The Auditor/Checker:** A separate process that verifies the claim against a physical source of truth (e.g., a Git commit, a test result, or a live API response).
3. **Promotion:** The status is only upgraded to `Checked` after independent verification.

---

## 🛠️ Current Project Strategy (Ghostkeep)
**Objective:** Implement a "Brain" that acts as a Verifiable Claims Register.

**Technical Path:**
- **Storage:** Move away from fuzzy narrative notes to a structured `Claims Register` in `\brain`.
- **Implementation:** 
    - Adopt the "Logbook Rule" (automatic capture of turns).
    - Build the **Auditor Agent** loop to handle the promotion of claims.
- **Tooling:** Explore the `Baton` repository (specifically the `tvardeniya` skill) as a blueprint for claim formatting, while building our own superior verification logic.

---

## 📝 Notes & Open Questions
- **The Baton Offer:** Stanimir is interested in how the "Checker" is implemented. This is a potential collaboration point.
- **Noise Filter:** By only promoting "Checked" claims to long-term memory, we naturally filter out the noise of daily coding sessions.
