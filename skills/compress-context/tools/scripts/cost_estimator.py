PRICES = {
    "claude-haiku-4": {"input": 0.25, "output": 1.25},
    "claude-sonnet-4": {"input": 3, "output": 15},
    "claude-opus-4": {"input": 15, "output": 75},
    "gpt-4.1": {"input": 2.5, "output": 10}
}

def estimate(n_calls, avg_in, avg_out, model, savings_rate, verify_overhead):
    input_price = PRICES[model]["input"]
    output_price = PRICES[model]["output"]
    
    baseline_cost = n_calls * (avg_in * input_price + avg_out * output_price) / 1_000_000
    comcom_cost = n_calls * (
        avg_in * (1 - savings_rate) * input_price +
        verify_overhead * input_price +
        avg_out * output_price
    ) / 1_000_000
    
    saved_usd = baseline_cost - comcom_cost
    percent_saved = (saved_usd / baseline_cost) * 100 if baseline_cost != 0 else 0
    
    return {
        "baseline_cost": baseline_cost,
        "comcom_cost": comcom_cost,
        "saved_usd": saved_usd,
        "percent_saved": percent_saved
    }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Estimate costs with COMCOM")
    parser.add_argument("--n_calls", type=int, required=True)
    parser.add_argument("--avg_in", type=float, required=True)
    parser.add_argument("--avg_out", type=float, required=True)
    parser.add_argument("--model", type=str, choices=PRICES.keys(), required=True)
    parser.add_argument("--savings_rate", type=float, required=True)
    parser.add_argument("--verify_overhead", type=float, required=True)
    
    args = parser.parse_args()
    
    result = estimate(
        args.n_calls,
        args.avg_in,
        args.avg_out,
        args.model,
        args.savings_rate,
        args.verify_overhead
    )
    
    print(f"Baseline Cost: ${result['baseline_cost']:.2f}")
    print(f"COMCOM Cost: ${result['comcom_cost']:.2f}")
    print(f"Saved USD: ${result['saved_usd']:.2f}")
    print(f"Percent Saved: {result['percent_saved']:.2f}%")