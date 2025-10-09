import json
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from rest_framework import serializers

from accounts.views_utils import generate_temp_password

from .serializers import CreateUserSerializer, CustomTokenObtainPairSerializer, SetPasswordSerializer
from django.core.mail import send_mail


# Create your views here.


class CustomTokenObtainPairView(TokenObtainPairView):
    permission_classes = (AllowAny,)
    serializer_class = CustomTokenObtainPairSerializer


class LogoutView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"message": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"message": "Logout successful."}, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            print("Logout error:", e)
            return Response({"message": "Invalid or expired refresh token."}, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class SetPasswordView(APIView):
    @extend_schema(
        request=SetPasswordSerializer,
        responses=serializers.Serializer,
        description="Set password"
    )
    def post(self, request, uidb64, token):
        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = get_user_model().objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, get_user_model().DoesNotExist):
            return JsonResponse({'message': 'Invalid link.'}, status=400)
        
        if not default_token_generator.check_token(user, token):
            return JsonResponse({'message': 'Invalid or expired token.'}, status=400)
        
        serializer = SetPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return JsonResponse({'message': serializer.errors}, status=400)
        
        password = serializer.validated_data['password']
        password2 = serializer.validated_data['password2']
        
        if password != password2:
            return JsonResponse({'message': 'Passwords do not match.'}, status=400)
        
        user.set_password(password)
        user.save()
        return JsonResponse({'message': 'Password set successfully. You can now log in.'}, status=200)


class CreateUserAPIView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=CreateUserSerializer,
        responses=serializers.Serializer,
        description="Create a new user and send invite email."
    )
    def post(self, request):
        username = request.data.get('username')
        email = request.data.get('email')
        role = request.data.get('role')
        if not username or not email or not role:
            return Response({'message': 'username, email, and role are required.'}, status=status.HTTP_400_BAD_REQUEST)

        User = get_user_model()
        if User.objects.filter(username=username).exists():
            return Response({'message': 'User with this username already exists.'}, status=status.HTTP_400_BAD_REQUEST)
        
        if User.objects.filter(email=email).exists():
            return Response({'message': 'User with this email already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        temp_password = generate_temp_password()
        user = User.objects.create(username=username, email=email, role=role)
        user.set_password(temp_password)
        user.save()

        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        invite_url = f"{settings.FRONTEND_URL}/login"

        subject = 'Welcome to HVAC Assist – Your Engineer Support Tool'
        html_message = render_to_string('accounts/invite_email.html', {
            'first_name': user.first_name or username,
            'login_url': invite_url,
            'username': username,
            'temp_password': temp_password,
        })

        send_mail(subject, '', settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False, html_message=html_message)

        return Response({'message': 'User created and invite sent successfully.', 'uid': uid, 'token': token}, status=status.HTTP_201_CREATED)


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth import get_user_model
from django.conf import settings
from .serializers import ForgotPasswordSerializer  # adjust path if needed

User = get_user_model()
from drf_yasg.utils import swagger_auto_schema
class ForgotPasswordAPIView(APIView):
    @extend_schema(
        request=ForgotPasswordSerializer,
        responses=serializers.Serializer,
        description="Forget password email."
    )
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'User with this email does not exist.'}, status=status.HTTP_404_NOT_FOUND)

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_url = f"{settings.FRONTEND_URL}/reset-password/?{uid}/{token}/"

        html_content = render_to_string('accounts/password_reset_email.html', {
            'username': user.get_full_name() or user.username,
            'reset_url': reset_url,
        })

        email_message = EmailMultiAlternatives(
            subject="Reset Your Password – HVAC Assist",
            body="Please use an HTML-compatible email viewer to see this message.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email]
        )
        email_message.attach_alternative(html_content, "text/html")
        email_message.send()

        return Response({
        'message': "We have successfully sent a password reset link to your registered email address. Please check your inbox to proceed.",
        'uid': uid,
        'token': token,
    }, status=status.HTTP_200_OK)


