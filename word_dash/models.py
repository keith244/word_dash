from django.db import models
from django.conf import settings

# Create your models here.

User = settings.AUTH_USER_MODEL

class Match(models.Model):
    STATUS_CHOICES = [
        ('waiting','Waiting'),
        ('in_progress','In Progress'),
        ('completed','Completed'),
    ]
    player1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='matches_as_p1')
    player2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='matches_as_p2')
    best_of = models.PositiveIntegerField(default=5)
    player1_score = models.PositiveIntegerField(default=0)
    player2_score = models.PositiveIntegerField(default=0)
    winner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='won_matches')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='waiting')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.player1} vs {self.player2}"
    
    def rounds_to_win(self):
        return (self.best_of // 2) + 1
    
class Round(models.Model):
    STATUS_CHOICES = [
        ('letter_pick','Letter Pick'),
        ('word_race','Word Race'),
        ('completed','Completed'),
    ]
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='rounds')
    round_number = models.PositiveIntegerField()
    first_letter_picker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='first_pick_rounds')
    second_letter_picker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='second_pick_rounds')
    first_letter = models.CharField(max_length=1, blank=True)
    second_letter = models.CharField(max_length=1, blank=True)
    winner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='won_rounds')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='letter_pick')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Match {self.match.id} - Round {self.round_number}"
    
    def pattern(self):
        return f"{self.first_letter} -> {self.second_letter}"
    
    
class WordSubmission(models.Model):
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name='submissions')
    player = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submissions')
    word = models.CharField(max_length=100)
    is_valid = models.BooleanField(default=False)
    is_winner = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.player} submitted '{self.word}'"
    
class Challenge(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
    ]

    challenger = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_challenges')
    opponent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_challenges')
    match = models.OneToOneField('Match', on_delete=models.SET_NULL, null=True, blank=True, related_name='challenge')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.challenger} challenged {self.opponent} — {self.status}"


class Notification(models.Model):
    TYPE_CHOICES = [
        ('challenge_received', 'Challenge Received'),
        ('challenge_accepted', 'Challenge Accepted'),
        ('challenge_declined', 'Challenge Declined'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    message = models.CharField(max_length=255)
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} — {self.type}"