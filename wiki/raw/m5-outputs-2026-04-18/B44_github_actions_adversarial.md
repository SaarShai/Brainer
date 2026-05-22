---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round9]
---

```yaml
name: Adversarial Benchmarking

on:
  pull_request:
    branches: [ main, develop ]

env:
  OLLAMA_API_KEY: ${{ secrets.OllamaApiKey }}
  DEFAULT_MODELS: "phi4,qwen3"
  TEMPERATURE: "0.7"
  TOP_P: "0.9"

jobs:
  adversarial-sweep:
    runs-on: ubuntu-22.04

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Setup Docker
        run: |
          apt-get update && apt-get install -y docker.io
          systemctl start docker
          docker login --username ${{ secrets.DOCKER_USERNAME }} --password ${{ secrets.DOCKER_PASSWORD }}

      - name: Run adversarial sweep with Ollama models
        id: ollama-run
        run: |
          ./adversarial_sweep.sh \
            --models $DEFAULT_MODELS \
            --temperature $TEMPERATURE \
            --top_p $TOP_P \
            --output results.json
        continue-on-error: true

      - name: Fallback to mocked judge if Ollama fails
        if: steps.ollama-run.outcome == 'failure'
        run: |
          ./mock_judge.py \
            --input test_cases/*.txt \
            --output fallback_results.json

      - name: Email results
        uses: dawidd6/action-send-email@v3
        with:
          server_address: smtp.example.com
          email_from: ci@example.com
          email_to: team@example.com
          subject: "Adversarial Benchmark Results"
          body: |
            PR #${{ github.event.pull_request.number }} has completed adversarial testing.
            Check the artifacts for detailed results.

      - name: Notify team via Slack
        uses: slackapi/slack-github-action@v1.23.0
        with:
          channel: '#ci-results'
          message: "Adversarial tests completed for PR #${{ github.event.pull_request.number }}"
```

This workflow:

1. Triggers on pull requests to main or develop branches
2. Sets up environment variables including Ollama API key and model parameters
3. Uses Ubuntu 22.04 runner with Docker support
4. Runs adversarial_sweep.sh with specified models (phi4 and qwen3)
5. Falls back to mock judge if Ollama integration fails
6. Notifies team via email and Slack
7. Continues running even if Ollama step fails

The workflow handles both successful and failed cases gracefully, ensuring feedback is always provided while maintaining the ability to test with real models when possible.

Key features:
- Automatic Docker setup
- Environment variable configuration
- Fallback mechanism for reliability
- Multiple notification channels
- Error handling and continuation
