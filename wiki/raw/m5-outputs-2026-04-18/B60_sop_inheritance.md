---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round10]
---

To design a system where multiple Standard Operating Procedures (SOPs) share common initial steps through an abstract SOP, follow this structured approach:

### Approach
1. **Identify Common Steps**: Analyze multiple SOPs to find shared initial steps that can be extracted into a common prefix.

2. **Create Abstract SOP**: Develop an `AbstractSOP` class containing these shared steps. This serves as the base class for all specific SOPs.

3. **Inheritance Mechanism**: Each specific SOP (e.g., `ChildSOP1`, `ChildSOP2`) inherits from `AbstractSOP`. They extend the common steps with their unique procedures.

4. **Step Execution**: Implement an `execute` method in each SOP class to run all steps sequentially, starting with inherited ones followed by specific steps.

### Example
Consider two coffee-making SOPs:

- **Espresso SOP**: Turn on machine → Grind beans → Add water → Brew.
- **Cappuccino SOP**: Turn on machine → Grind beans → Add milk → Steam milk → Brew.

**AbstractSOP** contains the common prefix: Turn on machine and Grind beans.

Each child SOP adds its unique steps:

```python
class AbstractSOP:
    def __init__(self):
        self.steps = ["Turn on machine", "Grind beans"]
    
    def execute(self):
        for step in self.steps:
            print(step)

class EspressoSOP(AbstractSOP):
    def __init__(self):
        super().__init__()
        self.steps.extend(["Add water", "Brew"])

class CappuccinoSOP(AbstractSOP):
    def __init__(self):
        super().__init__()
        self.steps.extend(["Add milk", "Steam milk", "Brew"])
```

### Algorithm
1. **Extract Common Steps**: Identify and list the initial steps common to all SOPs.
2. **Define Abstract Class**: Create `AbstractSOP` with these steps.
3. **Create Child Classes**: Each child class inherits from `AbstractSOP`, appending unique steps.
4. **Execution Flow**: When executing, each child runs all inherited steps followed by its specific ones.

### Benefits
- **Reduced Redundancy**: Common steps are maintained in one place.
- **Ease of Maintenance**: Updates to the abstract SOP affect all children.
- **Modularity**: Clear separation between shared and unique procedures.

This design promotes code reuse and simplifies updates, ensuring consistency across related SOPs.
