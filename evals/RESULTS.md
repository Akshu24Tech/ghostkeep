# Ghostkeep eval results

ghostkeep 0.3.2 · 30 labeled cases · python 3.11.15 · Windows

| Metric | Value | Items | Target | |
| --- | --- | --- | --- | --- |
| crashes | 0 |  | <= 0 | ok |
| capture_precision | 1.00 | 33/33 | >= 0.95 | ok |
| capture_recall | 1.00 | 32/32 | >= 0.95 | ok |
| count_accuracy | 1.00 | 24/24 | >= 0.95 | ok |
| verdict_accuracy | 1.00 | 22/22 | >= 0.95 | ok |
| orphan_precision | 1.00 | 3/3 | >= 1.0 | ok |
| orphan_recall | 1.00 | 3/3 | >= 1.0 | ok |
| attribution_accuracy | 1.00 | 12/12 | >= 1.0 | ok |
| decision_precision | 1.00 | 9/9 | >= 0.9 | ok |
| decision_recall | 1.00 | 8/8 | >= 0.9 | ok |
| unfinished_first | 1.00 | 3/3 | >= 1.0 | ok |
| handoff_facts | 1.00 | 5/5 | >= 1.0 | ok |
| secret_leaks | 0 |  | <= 0 | ok |
| injection_fenced | 1.00 | 1/1 | >= 1.0 | ok |
| handoff_max_60_lines | 1.00 | 30/30 | >= 1.0 | ok |

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
| agent_writes_git_hook_and_ignored_file | realdata | pass |
| same_decision_typed_into_two_tools | realdata | pass |
| antigravity_cli_json_encoded_args | realdata | pass |
| claude_deletes_file_with_bash | realdata | pass |
| interrupted_before_any_edit | realdata | pass |
| deleted_file_recreated_and_committed_later | realdata | pass |
| codex_agents_md_preamble_is_not_the_task | realdata | pass |
