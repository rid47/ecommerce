from django.shortcuts import render, get_object_or_404, redirect
# from django.http import HttpResponse
from .models import *
from django.core.exceptions import ObjectDoesNotExist
import stripe
from django.conf import settings
from django.contrib.auth.models import Group, User
from .forms import SignUpForm, ContactForm
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
# from django.core.paginator import Paginagor, EmptyPage, InvalidPage
from django.template.loader import get_template
from django.core.mail import EmailMessage


# Create your views here.


def home(request, category_slug=None):

    # return HttpResponse('<h1>Home</h1>')
    category_page = None
    products = None

    if category_slug is not None:
        category_page = get_object_or_404(Category, slug=category_slug)
        print(f"get_object_or_404 returned {category_page}")
        products = Product.objects.filter(category=category_page,
                                          available=True)
    else:
        products = Product.objects.all().filter(available=True)

    context = {

                'category': category_page,
                'products': products
    }
    return render(request, 'home.html', context)


def productPage(request, category_slug, product_slug):
    try:
        product = Product.objects.get(category__slug=category_slug, slug=product_slug)
    except Exception as e:
        raise e
    # return HttpResponse('<h1>About</h1>')
    if request.method == 'POST' and request.user.is_authenticated and request.POST ['content'].strip() != '':
        Review.objects.create(product=product,
                              user=request.user,
                              content=request.POST['content'])

    reviews = Review.objects.filter(product=product)

    return render(request, 'product.html', {'product': product, 'reviews': reviews})


# def cart(request):
#     return render(request, 'cart.html')


def _cart_id(request):
    cart = request.session.session_key
    if not cart:
        cart = request.session.create()
    return cart


def add_cart(request, product_id):
    product = Product.objects.get(id=product_id)
    print(f"Product is {product}")
    try:
        cart = Cart.objects.get(cart_id=_cart_id(request))
        print(f"Cart is {cart}")
    except Cart.DoesNotExist:
        cart = Cart.objects.create(

            cart_id=_cart_id(request)
            )
        print(f"Cart is {cart}")
        cart.save()
    try:
        cart_item = CartItem.objects.get(product=product, cart=cart)
        if cart_item.quantity < cart_item.product.stock:
            cart_item.quantity += 1
        cart_item.save()
    except CartItem.DoesNotExist:
        cart_item = CartItem.objects.create(

            product=product,
            quantity=1,
            cart=cart
            )
        cart_item.save()
    return redirect('cart_detail')


def cart_detail(request, total=0, counter=0, cart_items=None):
    print("inside cart_detail")
    try:
        cart = Cart.objects.get(cart_id=_cart_id(request))
        print(cart)
        cart_items = CartItem.objects.filter(cart=cart, active=True)
        for cart_item in cart_items:
            total += (cart_item.product.price * cart_item.quantity)
            counter += cart_item.quantity

        print(total)
        print(counter)
    except ObjectDoesNotExist:
        pass

    stripe.api_key = settings.STRIPE_SECRET_KEY
    stripe_total = int(total * 100)
    description = 'My Store'
    data_key = settings.STRIPE_PUBLISHABLE_KEY
    if request.method == 'POST':
        print(request.POST)
        try:
            token = request.POST['stripeToken']
            email = request.POST['stripeEmail']
            billingName = request.POST['stripeBillingName']
            billingAddress1 = request.POST['stripeBillingAddressLine1']
            billingCity = request.POST['stripeBillingAddressCity']
            billingPostcode = request.POST['stripeBillingAddressZip']
            billingCountry = request.POST['stripeBillingAddressCountryCode']
            shippingName = request.POST['stripeShippingName']
            shippingAddress1 = request.POST['stripeShippingAddressLine1']
            shippingCity = request.POST['stripeShippingAddressCity']
            shippingPostcode = request.POST['stripeShippingAddressZip']
            shippingCountry = request.POST['stripeShippingAddressCountryCode']
            customer = stripe.Customer.create(

                email=email,
                source=token
                )
            charge = stripe.Charge.create(

                amount=stripe_total,
                currency="usd",
                description=description,
                customer=customer.id

                )

        except stripe.error.CardError as e:
            return False, e

        # Creating the order
        try:
            order_details = Order.objects.create(
                token=token,
                total=total,
                emailAddress=email,
                billingName=billingName,
                billingAddress1=billingAddress1,
                billingCity=billingCity,
                billingPostcode=billingPostcode,
                billingCountry=billingCountry,
                shippingName=shippingName,
                shippingAddress1=shippingAddress1,
                shippingCity=shippingCity,
                shippingPostcode=shippingPostcode,
                shippingCountry=shippingCountry

                )
            order_details.save()
            for order_item in cart_items:
                or_item = OrderItem.objects.create(

                    product=order_item.product.name,
                    quantity=order_item.quantity,
                    price=order_item.product.price,
                    order=order_details

                    )
                or_item.save()

            # reduce stock

            products = Product.objects.get(id=order_item.product.id)
            products.stock = int(order_item.product.stock - order_item.quantity)
            products.save()
            order_item.delete()

            # print a msg when a order is created
            print('the order has been created')

            try:
                sendEmail(order_details.id)
                print("The order email has been sent")
            except IOError as e:
                return

            return redirect('thanks_page', order_details.id)
        except ObjectDoesNotExist:
            pass
    return render(request, 'cart.html',
                  dict(cart_items=cart_items, total=total, counter=counter, data_key=data_key, description=description, stripe_total=stripe_total))


def cart_remove(request,product_id):
    cart = Cart.objects.get(cart_id=_cart_id(request))
    product = get_object_or_404(Product, id=product_id)
    cart_item = CartItem.objects.get(product=product, cart=cart)
    if cart_item.quantity > 1:
        cart_item.quantity -= 1
        cart_item.save()
    else:
        cart_item.delete()
    return redirect('cart_detail')


def cart_remove_product(request, product_id):
    cart = Cart.objects.get(cart_id=_cart_id(request))
    product = get_object_or_404(Product, id=product_id)  # will return only one object
    cart_item = CartItem.objects.get(product=product, cart=cart)
    cart_item.delete()
    return redirect('cart_detail')


def thanks_page(request,order_id):
    if order_id:
        customer_order = get_object_or_404(Order, id=order_id)
    return render(request, 'thankyou.html', {'customer_order': customer_order})


def signupView(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            form.save()
            username = form.cleaned_data.get('username')
            signup_user = User.objects.get(username=username)
            customer_group = Group.objects.get(name='Customer')
            customer_group.user_set.add(signup_user)
    else:
        form = SignUpForm()
    return render(request, 'signup.html', {'form': form})


def signinView(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            print("Sign in form is valid")
            username = request.POST['username']
            password = request.POST['password']
            try:
                user = authenticate(username=username, password=password)
                print(f"User is {user}")
            except Exception as e:
                print(e)
                user = None
            if user is not None:
                login(request, user)
                return redirect('home')
            else:
                return redirect('signup')
    else:
        form = AuthenticationForm()
        return render(request, 'signin.html', {'form': form})


def signoutView(request):
    logout(request)
    return redirect('signin')


@login_required(redirect_field_name='next', login_url='signin')
def orderHistory(request):
    if request.user.is_authenticated:
        email = str(request.user.email)
        order_details = Order.objects.filter(emailAddress=email)
    return render(request, 'order_list.html', {'order_details': order_details})


@login_required(redirect_field_name='next', login_url='signin')
def viewOrder(request, order_id):
    if request.user.is_authenticated:
        email = str(request.user.email)
        order = Order.objects.get(id=order_id, emailAddress=email)
        order_items = OrderItem.objects.filter(order=order)
    return render(request, 'order_detail.html', {'order': order, 'order_items':order_items})


def search(request):
    products = Product.objects.filter(name__contains=request.GET['title'])
    return render(request, 'home.html', {'products': products})


def sendEmail(order_id):
    transaction = Order.objects.get(id=order_id)
    order_items = OrderItem.objects.filter(order=transaction)

    try:
        subject = "RMStore - New Order # {}".format(transaction.id)
        to = ['{}'.format(transaction.emailAddress)]
        from_email = "postmaster@sandboxf6b55d548d0f46dfb0cea888ac3f3032.mailgun.org"
        order_information = {
                            'transaction': transaction,
                            'order_items': order_items
                            }
        message = get_template('email/email.html').render(order_information)
        msg = EmailMessage(subject, message, to=to, from_email=from_email)
        msg.content_subtype = 'html'
        msg.send()
    except IOError as e:
        return e


def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            subject = form.cleaned_data.get('subject')
            from_email = form.cleaned_data.get('from_email')
            message = form.cleaned_data.get('message')
            name = form.cleaned_data.get('name')

            message_format = "{0} has sent you a new message:\n\n{1} from {2}".format(name, message, from_email)

            msg = EmailMessage(

                subject,
                message_format,
                to=['ridwanmizan@gmail.com'],
                from_email="postmaster@sandboxf6b55d548d0f46dfb0cea888ac3f3032.mailgun.org"
                )
            try:
                msg.send()
            except IOError as e:
                return e

            return render(request, 'contact_success.html')
    else:
        form = ContactForm()

    return render(request, 'contact.html', {'form': form})
