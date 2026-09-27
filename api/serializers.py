from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import KBEntry


class RegisterSerializer(serializers.Serializer):
    # No role field: every new company is a CLIENT via the model default.
    username     = serializers.CharField(max_length=150)
    password     = serializers.CharField(write_only=True)
    company_name = serializers.CharField(max_length=255)
    email        = serializers.EmailField()

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('A user with this username already exists.')
        return value

    def validate(self, attrs):
        # Run Django's AUTH_PASSWORD_VALIDATORS against the would-be user.
        validate_password(
            attrs['password'],
            User(username=attrs['username'], email=attrs['email']),
        )
        return attrs


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class KBQuerySerializer(serializers.Serializer):
    search = serializers.CharField(max_length=255)


class KBEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model  = KBEntry
        fields = ['id', 'question', 'answer', 'category']


class UsageSummaryFilterSerializer(serializers.Serializer):
    # Mapped from the ?from= / ?to= query params (`from` is a Python keyword).
    start = serializers.DateField(required=False)
    end   = serializers.DateField(required=False)

    def validate(self, attrs):
        if 'start' in attrs and 'end' in attrs and attrs['start'] > attrs['end']:
            raise serializers.ValidationError({'from': '`from` must be on or before `to`.'})
        return attrs
