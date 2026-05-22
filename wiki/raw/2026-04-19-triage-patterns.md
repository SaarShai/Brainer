---
type: raw
source: gemma4:26b
date: 2026-04-19
tags: [triage, model-routing, research]
---

The landscape of Large Language Model (LLM) deployment has transitioned from monolithic inference toward sophisticated routing architectures designed to navigate the cost-accuracy Pareto curve. As model capabilities diverge, the ability to triage tasks—directing simple queries to lightweight models and complex reasoning to frontier models—is critical for scalable, production-grade agentic systems.

**OpenRouter** acts as a unified gateway for accessing diverse LLM providers through a single, standardized API. *Routing Signal:* Provider availability and real-time latency metrics. *Integration Pattern:* API Proxy/Gateway.

**Martian** implements an intelligent routing layer that selects the optimal model for a specific prompt by predicting performance. *Routing Signal:* Small-LLM-based task complexity estimation. *Integration Pattern:* Model-as-a-Service (MaaS) routing.

**Not Diamond** automates model selection by evaluating prompt-model pairs against specific, high-fidelity benchmarks. *Routing Signal:* Embedding-based semantic similarity to known high-performing prompt patterns. *Integration Pattern:* Evaluation-driven selection.

**RouteLLM** provides an open-source framework for optimizing the trade-off between cost and performance via a learned router. *Routing Signal:* Small-LLM classifier or reward model. *Integration Pattern:* Middleware/Proxy-based routing.

**Anthropic Task Tool + `subagent_type`** enables structured delegation within an agentic loop by defining specialized sub-agents via tool definitions. *Routing Signal:* Tool-call schema and predefined sub-agent metadata. *Integration Pattern:* Agentic orchestration/Sub-agent instantiation.

**Claude Code’s `UserPromptSubmit` Hook System** allows developers to intercept and modify user input before it reaches the primary model. *Routing Signal:* Regex-based pattern matching or local heuristic analysis. *Integration Pattern:* Client-side/CLI-level middleware.

**The Orchestrator-Worker Pattern** utilizes a central controller to decompose complex, multi-step goals into discrete, manageable tasks for specialized agents. *Routing Signal:* Semantic intent decomposition via LLM-based planning. *Integration Pattern:* Distributed agentic architecture.

The fundamental driver for these patterns is the **Cost-Accuracy Pareto Curve**, where the objective is to maximize accuracy while minimizing the total cost per token. By identifying the "knee" of the curve, developers can route the majority of traffic to low-cost models (e.g., Haiku, Llama 3 8B) without degrading the overall system utility, reserving expensive frontier models only for tasks where the performance gain justifies the marginal cost.

**Design Ideas for a Claude Code "Triage Subagent" using local Ollama:**

1.  **Semantic Complexity Classifier:** Implement a local Llama 3 (8B) instance via Ollama to perform a zero-shot classification of the `UserPromptSubmit` payload into "Routine," "Reasoning," or "Coding" categories to determine the target model.
2.  **Regex-Heuristic Pre-filter:** Integrate a lightweight regex layer within the hook to intercept boilerplate commands (e.g., `ls`, `cat`, `git status`) to bypass LLM invocation entirely, routing directly to local shell execution.
3.  **Embedding-based Cache Lookup:** Generate embeddings for incoming prompts using a local `nomic-embed-text` model; if the cosine similarity to a "previously solved simple task" exceeds a threshold, return the cached response immediately.
4.  **Confidence-Based Escalation:** Utilize the logprobs from the local Ollama classifier; if the entropy of the predicted class is high (indicating uncertainty), escalate the task to a paid frontier model like Claude 3.5 Sonnet.
5.  **Token-Density Routing:** Calculate the prompt's token density and structural complexity; if the prompt is highly dense with structural code, route to a model with a larger context window, whereas sparse natural language prompts route to a smaller, faster model.
