from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()


class EmailBackend(ModelBackend):
    """
    Custom authentication backend that uses email instead of username.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate using email and password.
        The 'username' parameter is actually the email address.
        """
        if username is None:
            username = kwargs.get("email")

        if username is None or password is None:
            return None

        try:
            # Try to fetch the user by email
            user = User.objects.get(email__iexact=username)
        except User.DoesNotExist:
            # Run the default password hasher once to reduce the timing
            # difference between an existing and a non-existing user
            User().set_password(password)
            return None

        # Check the password and return the user if valid
        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None
