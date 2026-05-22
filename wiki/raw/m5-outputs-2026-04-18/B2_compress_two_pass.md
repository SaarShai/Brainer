---
type: raw
source: deepseek-r1:32b
date: 2026-04-18
tags: [m5-generated, round4]
---

Running ComCom twice—compressing text to make it smaller and then compressing it again—would likely save some additional space, but not as much as the first compression. The savings from the second run would be smaller because there's less redundancy left in the data after the first compression.

For example, if a 10MB file is compressed once to 5MB (a 50% reduction), compressing it again might only save another 0.5MB, making the total size 4.9MB. This means the second compression adds minimal savings compared to the first.

Using LLMLingua-2's perplexity scoring, we can measure how well a model predicts the text. Lower perplexity means better prediction and higher quality. After the first compression, the perplexity might be low, say 100. But after compressing again, the perplexity could increase to 120, indicating that the text is harder to predict and thus lower in quality.

So, while running ComCom twice does save a little more space, it doesn't compound the savings significantly and may reduce the quality of the compressed text. The second compression isn't as effective because there's less redundancy left to exploit.
