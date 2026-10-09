# 🛡️ Auditor Verification Protocol

## Role Definition
The Auditor's job is to move claims from `Unverified` $\rightarrow$ `Checked` or `Invalid`. An Auditor **never** trusts the word of the agent who wrote the claim.

## Verification Workflow
1. **Scan:** Find all rows in `claims_register.md` with the status `Unverified`.
2. **Investigate:**
    - For **Code Claims**: Check the actual files in the workspace or run the mentioned tests.
    - For **API Claims**: Perform a live request to the endpoint.
    - For **Decision Claims**: Look for the specific commit hash or meeting note.
3. **Update:**
    - If evidence exists $\rightarrow$ Change status to `Checked` and add the specific evidence (e.g., "Verified in commit xxxx").
    - If evidence is missing/wrong $\rightarrow$ Change status to `Invalid` and write a reason.

## Golden Rule
**No self-certification.** If the worker agent says "I checked it," it is still `Unverified` until the Auditor independently confirms it.
