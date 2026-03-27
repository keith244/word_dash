import json
import random
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings as django_settings
from .models import Match, Round, WordSubmission, Challenge, Notification
from django.contrib.auth import get_user_model
from .dictionary import is_valid_word
from django.db import transaction

User = get_user_model()


class MatchConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.match_id = self.scope['url_route']['kwargs']['match_id']
        self.match_group = f'match_{self.match_id}'
        self.user = self.scope['user']

        if not self.user.is_authenticated:
            await self.close()
            return

        await self.channel_layer.group_add(self.match_group, self.channel_name)
        await self.accept()

        await self.channel_layer.group_send(self.match_group, {
            'type': 'player_joined',
            'username': self.user.username,
        })

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.match_group, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')

        if action == 'pick_letter':
            await self.handle_letter_pick(data)

        elif action == 'submit_word':
            await self.handle_word_submission(data)

    # --- Letter pick ---
    async def handle_letter_pick(self, data):
        letter = data.get('letter', '').upper().strip()
        round_id = data.get('round_id')

        if not letter.isalpha() or len(letter) != 1:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid letter.'
            }))
            return

        updated_round = await self.save_letter(round_id, self.user.id, letter)

        if updated_round is None:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Not your turn to pick a letter.'
            }))
            return

        await self.channel_layer.group_send(self.match_group, {
            'type': 'letter_picked',
            'username': self.user.username,
            'letter': letter,
            'round_id': round_id,
            'first_letter': updated_round['first_letter'],
            'second_letter': updated_round['second_letter'],
            'status': updated_round['status'],
        })

    # --- Word submission ---
    async def handle_word_submission(self, data):
        word = data.get('word', '').lower().strip()
        round_id = data.get('round_id')

        if not word.isalpha():
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid word.'
            }))
            return

        result = await self.save_word(round_id, self.user.id, word)

        if result is None:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Submission failed — check letters or round status.'
            }))
            return

        await self.channel_layer.group_send(self.match_group, {
            'type': 'word_submitted',
            'username': self.user.username,
            'word': word,
            'is_valid': result['is_valid'],
            'is_winner': result['is_winner'],
            'round_id': round_id,
        })

        if result['is_winner']:
            await self.channel_layer.group_send(self.match_group, {
                'type': 'round_over',
                'winner': self.user.username,
                'round_id': round_id,
                'match_status': result['match_status'],
                'match_winner': result.get('match_winner'),
                'player1_score': result['player1_score'],
                'player2_score': result['player2_score'],
                'next_round_id': result.get('next_round_id'),
                'next_round_first_picker': self.user.username,  # winner always picks first next round

            })

    # --- DB operations ---
    @database_sync_to_async
    def save_letter(self, round_id, user_id, letter):
        try:
            round_obj = Round.objects.get(id=round_id, status='letter_pick')
        except Round.DoesNotExist:
            print(f"DEBUG save_letter: round {round_id} not found or not in letter_pick status")
            return None

        print(f"DEBUG save_letter: round {round_id} | user_id={user_id} | first_picker={round_obj.first_letter_picker.id} | second_picker={round_obj.second_letter_picker.id} | first_letter='{round_obj.first_letter}' | second_letter='{round_obj.second_letter}'")

        if round_obj.first_letter_picker.id == user_id and not round_obj.first_letter:
            round_obj.first_letter = letter
        elif round_obj.second_letter_picker.id == user_id and not round_obj.second_letter:
            round_obj.second_letter = letter
        else:
            print(f"DEBUG save_letter: rejected — not this user's turn")
            return None

        if round_obj.first_letter and round_obj.second_letter:
            round_obj.status = 'word_race'

        round_obj.save()

        return {
            'first_letter': round_obj.first_letter,
            'second_letter': round_obj.second_letter,
            'status': round_obj.status,
        }

    @database_sync_to_async
    def save_word(self, round_id, user_id, word):
        from django.db import transaction
        try:
            with transaction.atomic():
                round_obj = Round.objects.select_related('match').select_for_update().get(
                    id=round_id, status='word_race'
                )

                fl = round_obj.first_letter.lower()
                sl = round_obj.second_letter.lower()

                is_valid = (
                    len(word) >= 2 and
                    word[0] == fl and
                    word[-1] == sl and
                    is_valid_word(word)
                )

                if round_obj.winner is not None:
                    return None

                submission = WordSubmission.objects.create(
                    round=round_obj,
                    player_id=user_id,
                    word=word,
                    is_valid=is_valid,
                    is_winner=False,
                )

                if not is_valid:
                    return {
                        'is_valid': False,
                        'is_winner': False,
                        'match_status': round_obj.match.status,
                        'player1_score': round_obj.match.player1_score,
                        'player2_score': round_obj.match.player2_score,
                    }

                submission.is_winner = True
                submission.save()

                round_obj.winner_id = user_id
                round_obj.status = 'completed'
                round_obj.save()

                match = round_obj.match
                if match.player1_id == user_id:
                    match.player1_score += 1
                else:
                    match.player2_score += 1

                rounds_to_win = match.rounds_to_win()
                match_winner = None
                next_round_id = None

                if match.player1_score >= rounds_to_win:
                    match.status = 'completed'
                    match.winner_id = match.player1_id
                    match_winner = match.player1.username
                elif match.player2_score >= rounds_to_win:
                    match.status = 'completed'
                    match.winner_id = match.player2_id
                    match_winner = match.player2.username
                else:
                    next_round = Round.objects.create(
                        match=match,
                        round_number=round_obj.round_number + 1,
                        first_letter_picker_id=user_id,
                        second_letter_picker_id=(
                            match.player2_id if match.player1_id == user_id else match.player1_id
                        ),
                        status='letter_pick',
                    )
                    next_round_id = next_round.id

                match.save()

                return {
                    'is_valid': True,
                    'is_winner': True,
                    'match_status': match.status,
                    'match_winner': match_winner,
                    'player1_score': match.player1_score,
                    'player2_score': match.player2_score,
                    'next_round_id': next_round_id,
                }

        except Round.DoesNotExist:
            print(f"DEBUG save_word: round {round_id} not found or not in word_race status")
            return None

    # --- Group event handlers ---
    async def player_joined(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_joined',
            'username': event['username'],
        }))

    async def letter_picked(self, event):
        await self.send(text_data=json.dumps({
            'type': 'letter_picked',
            'username': event['username'],
            'letter': event['letter'],
            'round_id': event['round_id'],
            'first_letter': event['first_letter'],
            'second_letter': event['second_letter'],
            'status': event['status'],
        }))

    async def word_submitted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'word_submitted',
            'username': event['username'],
            'word': event['word'],
            'is_valid': event['is_valid'],
            'is_winner': event['is_winner'],
            'round_id': event['round_id'],
        }))

    async def round_over(self, event):
        await self.send(text_data=json.dumps({
            'type': 'round_over',
            'winner': event['winner'],
            'round_id': event['round_id'],
            'match_status': event['match_status'],
            'match_winner': event.get('match_winner'),
            'player1_score': event['player1_score'],
            'player2_score': event['player2_score'],
            'next_round_id': event.get('next_round_id'),
            'next_round_first_picker': event.get('next_round_first_picker'),
        }))
        
        
class LobbyConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            await self.close()
            return

        self.user_group = f'user_{self.user.id}'

        await self.channel_layer.group_add('lobby', self.channel_name)
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()

        await self.channel_layer.group_send('lobby', {
            'type': 'user_online',
            'user_id': self.user.id,
            'username': self.user.username,
        })

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard('lobby', self.channel_name)
        await self.channel_layer.group_discard(self.user_group, self.channel_name)

        await self.channel_layer.group_send('lobby', {
            'type': 'user_offline',
            'user_id': self.user.id,
            'username': self.user.username,
        })

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')

        if action == 'send_challenge':
            await self.handle_send_challenge(data)
        elif action == 'accept_challenge':
            await self.handle_accept_challenge(data)
        elif action == 'decline_challenge':
            await self.handle_decline_challenge(data)

    async def handle_send_challenge(self, data):
        opponent_id = data.get('opponent_id')
        opponent = await self.get_user(opponent_id)
        if not opponent:
            return

        # Check no pending challenge already exists
        existing = await self.get_pending_challenge(self.user.id, opponent_id)
        if existing:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'You already have a pending challenge with {opponent.username}.'
            }))
            return

        # Save challenge to DB
        challenge = await self.save_challenge(self.user.id, opponent_id)

        # Save notification for opponent
        await self.save_notification(
            user_id=opponent_id,
            notif_type='challenge_received',
            message=f'{self.user.username} challenged you to a match!',
            challenge_id=challenge.id,
        )

        # Try WebSocket — send to opponent if online
        await self.channel_layer.group_send(f'user_{opponent_id}', {
            'type': 'challenge_received',
            'challenger_id': self.user.id,
            'challenger': self.user.username,
            'challenge_id': challenge.id,
        })

        # Send email as fallback
        await self.send_challenge_email(opponent, challenge.id)

        await self.send(text_data=json.dumps({
            'type': 'challenge_sent',
            'opponent': opponent.username,
        }))

    async def handle_accept_challenge(self, data):
        challenge_id = data.get('challenge_id')
        challenge = await self.get_challenge(challenge_id)

        if not challenge or challenge.status != 'pending':
            return

        match_data = await self.create_match_from_challenge(challenge_id)

        # Notify challenger
        await self.save_notification(
            user_id=challenge.challenger_id,
            notif_type='challenge_accepted',
            message=f'{self.user.username} accepted your challenge!',
            challenge_id=challenge_id,
        )

        await self.channel_layer.group_send(f'user_{challenge.challenger_id}', {
            'type': 'challenge_accepted',
            'match_id': match_data['match_id'],
            'opponent': self.user.username,
        })

        await self.send(text_data=json.dumps({
            'type': 'challenge_accepted',
            'match_id': match_data['match_id'],
            'opponent': match_data['challenger_username'],
        }))

    async def handle_decline_challenge(self, data):
        challenge_id = data.get('challenge_id')
        challenge = await self.get_challenge(challenge_id)

        if not challenge:
            return

        await self.decline_challenge(challenge_id)

        # Notify challenger
        await self.save_notification(
            user_id=challenge.challenger_id,
            notif_type='challenge_declined',
            message=f'{self.user.username} declined your challenge.',
            challenge_id=challenge_id,
        )

        await self.channel_layer.group_send(f'user_{challenge.challenger_id}', {
            'type': 'challenge_declined',
            'opponent': self.user.username,
        })

    # --- DB operations ---
    @database_sync_to_async
    def get_user(self, user_id):
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def get_pending_challenge(self, challenger_id, opponent_id):
        return Challenge.objects.filter(
            challenger_id=challenger_id,
            opponent_id=opponent_id,
            status='pending'
        ).first()

    @database_sync_to_async
    def save_challenge(self, challenger_id, opponent_id):
        return Challenge.objects.create(
            challenger_id=challenger_id,
            opponent_id=opponent_id,
            status='pending',
        )

    @database_sync_to_async
    def get_challenge(self, challenge_id):
        try:
            return Challenge.objects.get(id=challenge_id)
        except Challenge.DoesNotExist:
            return None

    @database_sync_to_async
    def decline_challenge(self, challenge_id):
        Challenge.objects.filter(id=challenge_id).update(status='declined')

    @database_sync_to_async
    def save_notification(self, user_id, notif_type, message, challenge_id):
        Notification.objects.create(
            user_id=user_id,
            type=notif_type,
            message=message,
            challenge_id=challenge_id,
        )

    @database_sync_to_async
    def create_match_from_challenge(self, challenge_id):
        challenge = Challenge.objects.select_related('challenger', 'opponent').get(id=challenge_id)
        challenge.status = 'accepted'

        match = Match.objects.create(
            player1=challenge.challenger,
            player2=challenge.opponent,
            status='in_progress',
        )

        challenge.match = match
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

        return {
            'match_id': match.id,
            'challenger_username': challenge.challenger.username,
        }

    @database_sync_to_async
    def send_challenge_email(self, opponent, challenge_id):
        accept_url = f"http://127.0.0.1:8000/word_dash/challenge/{challenge_id}/accept/"
        decline_url = f"http://127.0.0.1:8000/word_dash/challenge/{challenge_id}/decline/"

        send_mail(
            subject=f'{self.user.username} challenged you to Word Dash!',
            message=(
                f'Hey {opponent.username},\n\n'
                f'{self.user.username} has challenged you to a Word Dash match!\n\n'
                f'Accept: {accept_url}\n'
                f'Decline: {decline_url}\n\n'
                f'Good luck!'
            ),
            from_email=django_settings.EMAIL_HOST_USER,
            recipient_list=[opponent.email],
            fail_silently=True,
        )

    # --- Group event handlers ---
    async def user_online(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_online',
            'user_id': event['user_id'],
            'username': event['username'],
        }))

    async def user_offline(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_offline',
            'user_id': event['user_id'],
            'username': event['username'],
        }))

    async def challenge_received(self, event):
        await self.send(text_data=json.dumps({
            'type': 'challenge_received',
            'challenger_id': event['challenger_id'],
            'challenger': event['challenger'],
            'challenge_id': event['challenge_id'],
        }))

    async def challenge_accepted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'challenge_accepted',
            'match_id': event['match_id'],
            'opponent': event['opponent'],
        }))

    async def challenge_declined(self, event):
        await self.send(text_data=json.dumps({
            'type': 'challenge_declined',
            'opponent': event['opponent'],
        }))