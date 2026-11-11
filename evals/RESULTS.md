# Ghostkeep eval results

ghostkeep 0.3.1 · 23 labeled cases · python 3.12.12 · Windows

| Metric | Value | Items | Target | |
| --- | --- | --- | --- | --- |
| crashes | 0 |  | <= 0 | ok |
| capture_precision | 1.00 | 25/25 | >= 0.95 | ok |
| capture_recall | 1.00 | 23/23 | >= 0.95 | ok |
| count_accuracy | 1.00 | 19/19 | >= 0.95 | ok |
| verdict_accuracy | 1.00 | 16/16 | >= 0.95 | ok |
| orphan_precision | 1.00 | 3/3 | >= 1.0 | ok |
| orphan_recall | 1.00 | 3/3 | >= 1.0 | ok |
| attribution_accuracy | 1.00 | 11/11 | >= 1.0 | ok |
| decision_precision | 1.00 | 6/6 | >= 0.9 | ok |
| decision_recall | 1.00 | 6/6 | >= 0.9 | ok |
| unfinished_first | 1.00 | 2/2 | >= 1.0 | ok |
| handoff_facts | 1.00 | 2/2 | >= 1.0 | ok |
| secret_leaks | 0 |  | <= 0 | ok |
| injection_fenced | 1.00 | 1/1 | >= 1.0 | ok |
| handoff_max_60_lines | 1.00 | 23/23 | >= 1.0 | ok |

| Case | Group | Result |
| --- | --- | --- |
| claude_edit_committed | core | pass |
| claude_edit_uncommitted | core | pass |
| ide_overclaims_lines | baseline | pass |
| ide_edit_left_pending | baseline | pass |
| ide_new_doc_and_chat_decision | baseline | pass |
| interrupted_claude_then_switch | baseline | pass |
| codex_apply_patch | core | pass |
| codex_shell_write | core | pass |
| codex_read_only_commands | precision | pass |
| true_orphan | core | pass |
| claimed_file_survives_unrelated_commit | history | pass |
| second_tool_continues_same_file | history | pass |
| sessions_from_another_repo | precision | pass |
| end_of_file_newline_edit | precision | pass |
| decision_false_positives | decisions | pass |
| injection_in_agent_message | safety | pass |
| secrets_never_stored | safety | pass |
| commit_hashes_not_redacted | safety | pass |
| malformed_logs_do_not_crash | safety | pass |
| claude_write_new_file | holdout | pass |
| antigravity_stopped_mid_step | holdout | pass |
| mixed_claimed_and_unknown_changes | holdout | pass |
| everyday_decision_language | holdout | pass |
