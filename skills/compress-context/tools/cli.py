import argparse
from pipeline_v2 import compress

def main():
    parser = argparse.ArgumentParser(description='Compress text with compression parameters')
    parser.add_argument('input_file', help='Input file path')
    parser.add_argument('--question', type=str, help='Question string')
    parser.add_argument('--rate', type=float, default=0.5, help='Compression rate (default: 0.5)')
    parser.add_argument('--show', action='store_true', help='Show compressed text')

    args = parser.parse_args()

    with open(args.input_file, 'r') as f:
        text = f.read()

    compressed_text, stats = compress(text, question=args.question, rate=args.rate)

    print("Compression statistics:", stats)
    if args.show:
        print("\nCompressed text:")
        print(compressed_text)

if __name__ == "__main__":
    main()
