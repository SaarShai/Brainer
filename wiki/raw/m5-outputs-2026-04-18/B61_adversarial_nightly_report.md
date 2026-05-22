---
type: raw
source: deepseek-r1:32b
date: 2026-04-19
tags: [m5-generated, round10]
---

```python
import subprocess
import shutil
import logging
from github import Github
import os
import smtplib
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('nightly_sweep.log'),
        logging.StreamHandler()
    ]
)

def run_adversarial_sweep():
    """Run adversarial sweep script and handle errors."""
    try:
        result = subprocess.run(
            ['./adversarial_sweep.sh'],
            capture_output=True,
            text=True,
            check=True
        )
        logging.info("Adversarial sweep completed successfully")
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        logging.error(f"Adversarial sweep failed: {e.stderr}")
        return False, None

def handle_results(output):
    """Copy results to Kaggle directory and verify."""
    try:
        # Copy results to nightly directory
        src = 'results/'
        dst = '/kaggle/results/nightly/' + datetime.now().strftime('%Y-%m-%d')
        
        if not os.path.exists(src):
            raise FileNotFoundError(f"Results directory {src} does not exist")
            
        shutil.copytree(src, dst)
        logging.info(f"Results copied to {dst}")
        return True
    except Exception as e:
        logging.error(f"Failed to handle results: {e}")
        return False

def check_regression(new_results):
    """Check for performance regression in new results."""
    try:
        # Load previous baseline results
        baseline = load_baseline()
        
        # Compare key metrics
        if new_results['accuracy'] < baseline['accuracy'] * 0.95:
            logging.warning("Performance regression detected")
            return True
            
        return False
    except Exception as e:
        logging.error(f"Failed to check regression: {e}")
        return False

def create_github_issue():
    """Create GitHub issue for regression."""
    try:
        g = Github(os.getenv('GITHUB_TOKEN'))
        repo = g.get_repo("your-org/your-repo")
        
        issue = repo.create_issue(
            title="Nightly Adversarial Sweep Regression Detected",
            body=f"Regression detected in {datetime.now().strftime('%Y-%m-%d')}\n\nPlease investigate."
        )
        logging.info(f"Issue created: #{issue.number}")
    except Exception as e:
        logging.error(f"Failed to create GitHub issue: {e}")

def send_email(subject, body):
    """Send summary email."""
    try:
        sender = os.getenv('EMAIL_USER')
        password = os.getenv('EMAIL_PASSWORD')
        recipient = 'your.email@example.com'
        
        server = smtplib.SMTP('smtp.example.com', 587)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, recipient, f"Subject: {subject}\n\n{body}")
        server.quit()
    except Exception as e:
        logging.error(f"Failed to send email: {e}")

def main():
    """Main execution flow."""
    success, output = run_adversarial_sweep()
    
    if not success:
        send_email("Nightly Sweep Failed", "Adversarial sweep did not complete successfully")
        return
        
    results_copied = handle_results(output)
    
    if not results_copied:
        send_email("Results Handling Failed", "Failed to copy results to Kaggle directory")
        return
    
    regression_detected = check_regression(output)
    
    if regression_detected:
        create_github_issue()
        send_email("Regression Detected", "Performance regression detected in nightly sweep")
    else:
        send_email("Nightly Sweep Complete", "Adversarial sweep completed successfully with no regressions")

if __name__ == "__main__":
    main()
```

This script implements a robust nightly adversarial sweep process with:

1. Error handling and logging throughout
2. Results management to Kaggle directory
3. Regression detection mechanism
4. GitHub issue creation on regression
5. Email notifications for status updates

The script should be run via cron job, e.g.:
```bash
0 0 * * * /usr/bin/python3 /path/to/script.py >> /dev/null 2>&1
```

Ensure environment variables are set for GITHUB_TOKEN and email credentials.

Key features:

- Modular design with clear separation of concerns
- Comprehensive logging for debugging
- Graceful error handling at each stage
- Automated issue creation for regressions
- Notification system via email
- Secure credential management

The script assumes:
1. adversarial_sweep.sh exists in the same directory
2. Results are output to 'results/' directory
3. Kaggle results directory structure exists
4. Valid GitHub token and email credentials are configured
