from django.db import models


class Type(models.Model):
    type_id = models.AutoField(primary_key=True)
    type_name = models.CharField(max_length=45)
    explanation = models.CharField(max_length=45)
    explanation2 = models.CharField(max_length=300)
    product = models.CharField(max_length=45)
    product_url = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'type'

    def __str__(self):
        return self.type_name


class MoniUser(models.Model):   # ← User 이름 변경
    user_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=45)
    email = models.CharField(max_length=45, null=True, blank=True)
    ID = models.CharField(max_length=45)
    password = models.CharField(max_length=128)

    type = models.ForeignKey(
        Type,
        on_delete=models.SET_NULL,
        db_column='type_id',
        null=True,
        related_name='users'
    )

    class Meta:
        managed = False
        db_table = 'user'

    def __str__(self):
        return self.name


class Goal(models.Model):
    goal_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        MoniUser,
        on_delete=models.CASCADE,
        db_column='user_id',
        related_name='goals'
    )
    title = models.CharField(max_length=45)
    target_amount = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'goal'

    def __str__(self):
        return f'{self.user.name} - {self.title}'


class BankAccount(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        MoniUser,
        on_delete=models.CASCADE,
        db_column='user_id',
        related_name='bank_accounts'
    )
    category = models.CharField(max_length=45)
    bank = models.CharField(max_length=45)
    balance = models.FloatField()

    class Meta:
        managed = False
        db_table = 'bank_account'

    def __str__(self):
        return f'{self.user.name} - {self.bank or ""}'


class Spending(models.Model):
    spending_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        MoniUser,
        on_delete=models.CASCADE,
        db_column='user_id',
        related_name='spendings'
    )
    category = models.CharField(max_length=45, null=True, blank=True)
    spend_date = models.DateTimeField()
    method = models.CharField(max_length=45)
    price = models.FloatField()
    details = models.CharField(max_length=45)
    transaction_type = models.CharField(max_length=45)
    memo = models.CharField(max_length=45)

    class Meta:
        managed = False
        db_table = 'spending'

    def __str__(self):
        return f'{self.user.name} - {self.price}'


class SpendingTypeJob(models.Model):
    """소비유형 분석 Job"""

    STATUS_CHOICES = [
        ("PENDING", "대기중"),
        ("RUNNING", "분석중"),
        ("DONE", "완료"),
        ("FAILED", "실패"),
    ]

    user = models.ForeignKey(MoniUser, on_delete=models.CASCADE)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")

    # 분석 결과 → Type FK 로 연결
    result_type = models.ForeignKey(
        Type,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True  # Job 은 새로 만들 테이블 → True 로 두기

    def __str__(self):
        return f"{self.user.name} - {self.status}"


class Notification(models.Model):

    id = models.AutoField(primary_key=True)
     
    user = models.ForeignKey(
        MoniUser,
        on_delete=models.CASCADE,
        related_name="notifications"
    )

    notification_time = models.DateTimeField(
        auto_now_add=True
    )

    notification_detail = models.CharField(
        max_length=500
    )

    class Meta:
        db_table = "notification"
        managed = False

    def __str__(self):
        return f"{self.user.name} - {self.notification_time}"