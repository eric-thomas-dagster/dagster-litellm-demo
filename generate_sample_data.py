"""
Generate realistic sample ticket data for demo.

Creates two datasets:
1. Small dataset (tickets_small.json) - For non-partitioned assets (quick demos)
2. Large dataset (tickets_large.json) - For partitioned assets (production simulation)

Usage:
    # Generate with defaults (60 historical, 30 future days)
    python generate_sample_data.py

    # Custom date ranges
    python generate_sample_data.py --historical-days 90 --future-days 60

    # Control ticket volume (avg tickets per weekday)
    python generate_sample_data.py --weekday-tickets 10 --weekend-tickets 3

    # Generate only large dataset
    python generate_sample_data.py --large-only

    # Generate only small dataset (7 days for demo)
    python generate_sample_data.py --small-only
"""

import argparse
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

# Ticket templates with realistic scenarios
TICKET_TEMPLATES = [
    # Access issues
    {
        "subject": "Can't login to my account",
        "body": "Hi support team,\n\nI've been trying to login for the past hour but keep getting 'invalid credentials' error. I'm 100% certain my password is correct because I have it saved in my password manager.\n\nThis is really urgent as I need to submit a critical report by end of day. Please help ASAP!",
        "category": "access",
    },
    {
        "subject": "Account locked after failed login attempts",
        "body": "My account has been locked after I mistyped my password a few times. I tried the 'forgot password' link but haven't received any reset email (checked spam folder too).\n\nCan you please unlock my account or manually send me a password reset link?",
        "category": "access",
    },
    {
        "subject": "Can't access shared workspace",
        "body": "My colleague shared a workspace with me last week but I still can't see it in my workspace list. I've tried logging out and back in, clearing cache, different browsers - nothing works.\n\nCan you check permissions on your end?",
        "category": "access",
    },
    # Bugs
    {
        "subject": "URGENT: Production database is down!!!",
        "body": "EMERGENCY - Our entire production database cluster is completely unresponsive. All customer-facing requests are failing with 503 errors. This is affecting 100% of our users.\n\nWe need IMMEDIATE assistance. This is a P0 incident. Please escalate to your on-call engineering team right away.",
        "category": "bug",
    },
    {
        "subject": "Mobile app crashes on startup",
        "body": "The iOS app crashes immediately when I open it. I've tried reinstalling but same issue. iPhone 14 Pro, iOS 17.2. This started after the latest update yesterday.",
        "category": "bug",
    },
    {
        "subject": "Data export incomplete",
        "body": "I exported my data yesterday but the CSV file only contains 1000 rows. I should have around 5000 records in my account. Is there a limit on exports?",
        "category": "bug",
    },
    {
        "subject": "Slow dashboard load times",
        "body": "The dashboard is taking 20-30 seconds to load for the past week. It used to load instantly. Is there a performance issue? We have about 50,000 records in our account.",
        "category": "bug",
    },
    # How-to / Questions
    {
        "subject": "How do I export my data?",
        "body": "Hi, I need to export all my project data to CSV for a quarterly report. I looked through the documentation but couldn't find clear instructions. Could you walk me through the steps?",
        "category": "how_to",
    },
    {
        "subject": "File upload size limit?",
        "body": "When I try to upload files larger than 10MB, the upload just hangs and eventually times out. Is there a file size limit? I need to upload project files that are 25-30MB.",
        "category": "how_to",
    },
    {
        "subject": "SSO setup help needed",
        "body": "We're trying to set up SAML SSO with Okta but getting 'invalid assertion' errors. We followed the documentation exactly. Can someone from your team help troubleshoot this?",
        "category": "how_to",
    },
    # Billing
    {
        "subject": "Billing question - double charged",
        "body": "I noticed I was charged twice this month for my subscription - $99 on Jan 1st and again on Jan 5th. My plan is only supposed to be $99/month.\n\nCan you please investigate and refund the duplicate charge? I have screenshots if needed.",
        "category": "billing",
    },
    {
        "subject": "Enterprise pricing inquiry",
        "body": "We're interested in upgrading to Enterprise for our 500-person team. What's the pricing and what additional features do we get? Can we schedule a call to discuss our requirements?",
        "category": "billing",
    },
    # Feature requests
    {
        "subject": "Feature request: Dark mode",
        "body": "Would love to see a dark mode option in the app. I spend 8+ hours a day using your software and my eyes really hurt after extended periods. Many other users would appreciate this too!",
        "category": "feature_request",
    },
    {
        "subject": "Integration with Salesforce?",
        "body": "Do you have a Salesforce integration? We'd like to sync our customer data automatically. If not, are you planning to build one? This would be a game-changer for us.",
        "category": "feature_request",
    },
    {
        "subject": "API rate limits too restrictive",
        "body": "We're building an integration with your API but keep hitting rate limits (100 req/min). For our use case, we need at least 500 req/min.\n\nIs there an enterprise plan or way to increase our limits? We're willing to pay more.",
        "category": "feature_request",
    },
    # Security
    {
        "subject": "Security concern - potential XSS vulnerability",
        "body": "Hi security team,\n\nI believe I've found a potential XSS vulnerability in your user profile page. When users enter certain characters in the bio field, they're not properly escaped.\n\nI'm a security researcher and would like to report this responsibly. Please let me know the best way to share technical details.",
        "category": "other",
    },
    {
        "subject": "GDPR data deletion request",
        "body": "Per GDPR regulations, I'm requesting complete deletion of all my personal data from your systems. Please confirm when this is completed.\n\nMy account email: user@example.com",
        "category": "other",
    },
    # Positive feedback
    {
        "subject": "Love the new update!",
        "body": "Just wanted to say the new dashboard redesign is fantastic! So much cleaner and faster. Great work team!\n\nOne small suggestion: would be nice to have keyboard shortcuts for common actions.",
        "category": "other",
    },
    # Technical issues
    {
        "subject": "Webhook notifications stopped working",
        "body": "Our webhooks stopped receiving notifications yesterday around 3pm EST. We haven't changed our endpoint configuration. Can you check if there's an issue on your end?",
        "category": "bug",
    },
    {
        "subject": "Password reset email not arriving",
        "body": "I requested a password reset 3 times but haven't received any emails. I checked spam folder too. Can you manually reset my password or resend the email?",
        "category": "access",
    },
]

CUSTOMER_NAMES = [
    "Alice Johnson", "Bob Smith", "Carol White", "Diana Lee", "Ethan Davis",
    "Fiona Chen", "Greg Thompson", "Hannah Park", "Ian Martinez", "Julia Wilson",
    "Kevin Brown", "Laura Green", "Mike Taylor", "Nina Schmidt", "Oscar Kim",
    "Paula Anderson", "Quinn Roberts", "Rachel Lee", "Steve Wilson", "Tina Foster",
]

SOURCES = ["zendesk", "intercom", "jira", "email"]


def generate_tickets(
    start_date: datetime,
    end_date: datetime,
    weekday_min: int = 3,
    weekday_max: int = 8,
    weekend_min: int = 0,
    weekend_max: int = 3,
) -> list[dict]:
    """Generate tickets for the given date range with configurable volume."""
    tickets = []
    ticket_id = 1
    current_date = start_date

    while current_date <= end_date:
        # Vary ticket volume by day of week
        day_of_week = current_date.weekday()  # 0 = Monday, 6 = Sunday

        if day_of_week < 5:  # Weekday
            num_tickets = random.randint(weekday_min, weekday_max)
        else:  # Weekend
            num_tickets = random.randint(weekend_min, weekend_max)

        # Generate tickets for this day
        for _ in range(num_tickets):
            template = random.choice(TICKET_TEMPLATES)

            # Random time during business hours (9am-6pm)
            hour = random.randint(9, 17)
            minute = random.randint(0, 59)
            timestamp = current_date.replace(hour=hour, minute=minute, second=0)

            ticket = {
                "id": f"T-{ticket_id:04d}",
                "subject": template["subject"],
                "body": template["body"],
                "customer_name": random.choice(CUSTOMER_NAMES),
                "customer_email": f"user{ticket_id}@example.com",
                "created_at": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source": random.choice(SOURCES),
            }
            tickets.append(ticket)
            ticket_id += 1

        current_date += timedelta(days=1)

    return tickets


def save_tickets(tickets: list[dict], filename: str, label: str):
    """Save tickets to JSON file."""
    output_file = Path(__file__).parent / "sample_data" / filename
    output_file.parent.mkdir(exist_ok=True)

    with open(output_file, "w") as f:
        json.dump(tickets, f, indent=2)

    print(f"✅ {label}: {len(tickets)} tickets → {filename}")
    return output_file


def main():
    """Generate and save sample ticket data."""
    parser = argparse.ArgumentParser(
        description="Generate sample ticket data for Dagster demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate with defaults
  python generate_sample_data.py

  # Generate 90 days historical + 60 days future
  python generate_sample_data.py --historical-days 90 --future-days 60

  # High-volume scenario (more tickets per day)
  python generate_sample_data.py --weekday-tickets 15 --weekend-tickets 5

  # Generate only large dataset for partitioned assets
  python generate_sample_data.py --large-only

  # Generate only small dataset for quick demos
  python generate_sample_data.py --small-only --small-days 5
        """,
    )

    # Date range options
    parser.add_argument(
        "--historical-days",
        type=int,
        default=60,
        help="Number of historical days (default: 60)",
    )
    parser.add_argument(
        "--future-days",
        type=int,
        default=30,
        help="Number of future days (default: 30)",
    )

    # Ticket volume options
    parser.add_argument(
        "--weekday-tickets",
        type=int,
        nargs=2,
        metavar=("MIN", "MAX"),
        default=[3, 8],
        help="Min and max tickets per weekday (default: 3 8)",
    )
    parser.add_argument(
        "--weekend-tickets",
        type=int,
        nargs=2,
        metavar=("MIN", "MAX"),
        default=[0, 3],
        help="Min and max tickets per weekend day (default: 0 3)",
    )

    # Small dataset options
    parser.add_argument(
        "--small-days",
        type=int,
        default=7,
        help="Number of days for small dataset (default: 7)",
    )

    # Generation mode
    parser.add_argument(
        "--large-only",
        action="store_true",
        help="Generate only large dataset",
    )
    parser.add_argument(
        "--small-only",
        action="store_true",
        help="Generate only small dataset",
    )

    args = parser.parse_args()

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    print("=" * 60)
    print("Generating Sample Ticket Data")
    print("=" * 60)

    # Generate large dataset (for partitioned assets)
    if not args.small_only:
        print(f"\n📦 Large Dataset (for partitioned assets)")
        print(f"   Date range: {args.historical_days} days back + {args.future_days} days forward")
        print(f"   Volume: {args.weekday_tickets[0]}-{args.weekday_tickets[1]} tickets/weekday")

        start_date = today - timedelta(days=args.historical_days)
        end_date = today + timedelta(days=args.future_days)

        large_tickets = generate_tickets(
            start_date,
            end_date,
            weekday_min=args.weekday_tickets[0],
            weekday_max=args.weekday_tickets[1],
            weekend_min=args.weekend_tickets[0],
            weekend_max=args.weekend_tickets[1],
        )

        save_tickets(large_tickets, "tickets_large.json", "Large dataset")

        total_days = (end_date - start_date).days + 1
        print(f"   Average: {len(large_tickets) / total_days:.1f} tickets/day")
        print(f"   Historical: {start_date.date()} to {today.date()}")
        print(f"   Future: {(today + timedelta(days=1)).date()} to {end_date.date()}")

    # Generate small dataset (for non-partitioned assets)
    if not args.large_only:
        print(f"\n📦 Small Dataset (for non-partitioned assets)")
        print(f"   Date range: {args.small_days} days (recent history)")
        print(f"   Volume: Lower volume for quick demos")

        # Small dataset: just recent days for quick demos
        start_date = today - timedelta(days=args.small_days)
        end_date = today

        # Lower volume for small dataset (fewer tokens used)
        small_tickets = generate_tickets(
            start_date,
            end_date,
            weekday_min=2,
            weekday_max=4,
            weekend_min=0,
            weekend_max=2,
        )

        save_tickets(small_tickets, "tickets_small.json", "Small dataset")

        total_days = (end_date - start_date).days + 1
        print(f"   Average: {len(small_tickets) / total_days:.1f} tickets/day")
        print(f"   Date range: {start_date.date()} to {end_date.date()}")

    print("\n" + "=" * 60)
    print("✅ Data generation complete!")
    print("=" * 60)
    print("\nUsage:")
    if not args.large_only:
        print("  - Non-partitioned assets use: sample_data/tickets_small.json")
    if not args.small_only:
        print("  - Partitioned assets use: sample_data/tickets_large.json")
    print()


if __name__ == "__main__":
    main()
