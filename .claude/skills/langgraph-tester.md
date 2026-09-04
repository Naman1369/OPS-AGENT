---
name: test-agent-pipeline
description: Use when you need to verify the LangGraph state transitions and agent handoffs for the OPS-AGENT pipeline.
---

# Agent Pipeline Verification Skill

1. **Initialize State:** Create a mock IT support ticket payload (e.g., "User cannot connect to the VPN, error code 809").
2. **Execute Intake:** Run the Intake Agent node. Verify it outputs a category, priority, and extracted keywords.
3. **Execute Retrieval:** Pass the keywords to the mock Vector DB. Verify context documents are appended to the state.
4. **Execute Resolution:** Run the Resolution Agent. Verify it generates a solution and outputs a raw confidence score.
5. **Execute Governance:** Run the Governance Agent. Verify it correctly flags the ticket as "Safe" or "Unsafe" based on a mock threshold.
6. **Output Evidence:** Print the final LangGraph state dictionary to the console to verify all steps completed sequentially without data loss.