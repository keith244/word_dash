"""
Debug script to check the state of a match and round.
Usage: python manage.py shell < debug_round.py

Or manually:
  python manage.py shell
  exec(open('debug_round.py').read())
"""

from word_dash.models import Match, Round
from django.contrib.auth import get_user_model

User = get_user_model()

# Get the most recent match
match = Match.objects.order_by('-created_at').first()

if not match:
    print("❌ No matches found")
else:
    print(f"✓ Match ID: {match.id}")
    print(f"  Player 1: {match.player1.username} (ID: {match.player1.id})")
    print(f"  Player 2: {match.player2.username} (ID: {match.player2.id})")
    print(f"  Status: {match.status}")
    print(f"  Score: {match.player1_score} - {match.player2_score}")
    print()

    rounds = match.rounds.all().order_by('round_number')
    print(f"Rounds: {len(rounds)}")
    
    for r in rounds:
        print(f"\n  Round {r.round_number}:")
        print(f"    Status: {r.status}")
        print(f"    First picker: {r.first_letter_picker.username} (ID: {r.first_letter_picker.id})")
        print(f"    Second picker: {r.second_letter_picker.username} (ID: {r.second_letter_picker.id})")
        print(f"    First letter: '{r.first_letter}' (empty: {not r.first_letter})")
        print(f"    Second letter: '{r.second_letter}' (empty: {not r.second_letter})")
        print(f"    Winner: {r.winner.username if r.winner else 'None'}")
    
    print()
    # Now check which rounds would be returned by the view query
    current = match.rounds.filter(
        status__in=['letter_pick', 'word_race']
    ).order_by('round_number').last()
    
    print(f"Current round (via view query):")
    if current:
        print(f"  ID: {current.id}")
        print(f"  Round number: {current.round_number}")
        print(f"  Status: {current.status}")
    else:
        print(f"  None (no letter_pick or word_race rounds found)")
