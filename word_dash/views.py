from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from .models import Match,Round
import random
from django.http import JsonResponse

# Create your views here.

User = get_user_model()

@login_required
def lobby(request):
    users = User.objects.exclude(id=request.user.id)
    active_matches = Match.objects.filter(
        status__in = ['waiting','in_progress']
    ).filter(
        player1 = request.user
    ) | Match.objects.filter(
        status__in = ['waiting','in_progress']
    ).filter(
        player2 = request.user
    )
    
    return render(request, 'word_dash/lobby.html',{
        'users':users,
        'active_matches':active_matches,
    })
    

@login_required
def start_match(request, user_id):
    opponent =get_object_or_404(User, id = user_id)
    
    if opponent == request.user:
        return redirect('lobby')
    
    # does match exist between these 2 players?
    existing = Match.objects.filter(
        status__in =['waiting','in_progress']
    ).filter(
        player1 = request.user, player2 = opponent
    ) | Match.objects.filter(
        status__in= ['waiting','in_progress']
    ).filter(
        player1 = opponent, player2=request.user
    )
    
    if existing.exists():
        return redirect('match',match_id=existing.first().id)
    
    # create match if none 
    match = Match.objects.create(
        player1=request.user,
        player2=opponent,
        status='in_progress',
    )

    # Randomly decide who picks first
    first_picker = random.choice([request.user, opponent])
    second_picker = opponent if first_picker == request.user else request.user

    # Create round 1
    Round.objects.create(
        match=match,
        round_number=1,
        first_letter_picker=first_picker,
        second_letter_picker=second_picker,
        status='letter_pick',
    )

    return redirect('match', match_id=match.id)


@login_required
def match_view(request, match_id):
    match = get_object_or_404(Match, id=match_id)

    if request.user not in [match.player1, match.player2]:
        return redirect('lobby')

    current_round = match.rounds.filter(
        status__in=['letter_pick', 'word_race']
    ).order_by('round_number').last()

    opponent = match.player2 if request.user == match.player1 else match.player1

    return render(request, 'word_dash/match.html', {
        'match': match,
        'opponent': opponent,
        'current_round': current_round,
        'user': request.user,
    })


@login_required
def search_users(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 1:
        return JsonResponse({'users': []})

    users = User.objects.filter(
        username__icontains=query
    ).exclude(
        id=request.user.id
    ).values('id', 'username')[:10]

    return JsonResponse({'users': list(users)})

from .models import Match, Round, Challenge, Notification

@login_required
def accept_challenge(request, challenge_id):
    challenge = get_object_or_404(Challenge, id=challenge_id, opponent=request.user, status='pending')

    match = Match.objects.create(
        player1=challenge.challenger,
        player2=challenge.opponent,
        status='in_progress',
    )

    challenge.match = match
    challenge.status = 'accepted'
    challenge.save()

    first_picker = random.choice([challenge.challenger, challenge.opponent])
    second_picker = challenge.opponent if first_picker == challenge.challenger else challenge.challenger

    Round.objects.create(
        match=match,
        round_number=1,
        first_letter_picker=first_picker,
        second_letter_picker=second_picker,
        status='letter_pick',
    )

    Notification.objects.create(
        user=challenge.challenger,
        type='challenge_accepted',
        message=f'{request.user.username} accepted your challenge!',
        challenge=challenge,
    )

    return redirect('match', match_id=match.id)


@login_required
def decline_challenge(request, challenge_id):
    challenge = get_object_or_404(Challenge, id=challenge_id, opponent=request.user, status='pending')
    challenge.status = 'declined'
    challenge.save()

    Notification.objects.create(
        user=challenge.challenger,
        type='challenge_declined',
        message=f'{request.user.username} declined your challenge.',
        challenge=challenge,
    )

    return redirect('lobby')


@login_required
def notifications_view(request):
    notifications = Notification.objects.filter(
        user=request.user
    ).order_by('-created_at')[:20]

    # Mark unread as read
    Notification.objects.filter(
        user=request.user, is_read=False
    ).update(is_read=True)

    return JsonResponse({
        'notifications': list(notifications.values(
            'id', 'type', 'message', 'is_read', 'created_at', 'challenge_id'
        ))
    })