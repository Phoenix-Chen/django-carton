from decimal import Decimal

from django.conf import settings

from carton import module_loading
from carton import settings as carton_settings


class CartItem(object):
    """
    A cart item, with the associated product, its quantity and its price.
    """
    def __init__(self, product, options, quantity):
        self.product = product
        self.options = options
        self.quantity = int(quantity)

    def __repr__(self):
        return u'CartItem Object (%s)' % self.product

    def to_dict(self):
        return {
            'product_pk': self.product.pk,
            'option_pks': [i.pk for i in self.options],
            'quantity': self.quantity
        }

    @property
    def subtotal(self):
        """
        Subtotal for the cart item.
        """
        return (self.product.price + sum([i.price for i in self.options])) * self.quantity


class Cart(object):

    """
    A cart that lives in the session.
    """
    def __init__(self, session, session_key=None):
        self._items_dict = []
        self.session = session
        self.session_key = session_key or carton_settings.CART_SESSION_KEY
            # If a cart representation was previously stored in session, then we
        if self.session_key in self.session:
            # rebuild the cart object from that serialized representation.
            cart_representation = self.session[self.session_key]
            products_cache = {}
            options_cache = {}
            for item in cart_representation:
                try:
                    product = None
                    if item.product_pk in products_cache:
                        product = products_cache[item.product_pk]
                    else:
                        product = self.get_product_queryset().get(pk=item.product_pk)
                        products_cache[item.product_pk] = product

                    options = []
                    for option_pk in item.option_pks:
                        if option_pk in options_cache:
                            options.append(options_cache[option_pk])
                        else:
                            option = self.get_option_queryset().get(pk=option_pk)
                            options.append(option)
                            options_cache[option_pk] = option
                    self._items_dict.append(CartItem(
                        product, options, item['quantity']
                    ))
                except Exception as e:
                    print(e)

    def __contains__(self, product, options=[]):
        """
        Checks if the given product is in the cart.
        """
        return self.__index__(product, options) != -1

    def __index__(self, product, options=[]):
        """
        Return the index of the product with options in _items_dict. Return -1 if not found.
        """
        cart_items = self.cart_serializable
        for i in range(len(cart_items)):
            if cart_items[i].product_pk == product.pk:
                if sorted(cart_items[i].option_pks) == sorted([i.pk for i in options]):
                    return i
        return -1

    def get_product_model(self):
        return module_loading.get_product_model()

    def get_option_model(self):
        return module_loading.get_option_model()

    def filter_products(self, queryset):
        """
        Applies lookup parameters defined in settings.
        """
        lookup_parameters = getattr(settings, 'CART_PRODUCT_LOOKUP', None)
        if lookup_parameters:
            queryset = queryset.filter(**lookup_parameters)
        return queryset

    def filter_options(self, queryset):
        """
        Applies lookup parameters defined in settings.
        """
        lookup_parameters = getattr(settings, 'CART_OPTION_LOOKUP', None)
        if lookup_parameters:
            queryset = queryset.filter(**lookup_parameters)
        return queryset

    def get_product_queryset(self):
        product_model = self.get_product_model()
        queryset = product_model._default_manager.all()
        queryset = self.filter_products(queryset)
        return queryset

    def get_option_queryset(self):
        option_model = self.get_option_model()
        queryset = option_model._default_manager.all()
        queryset = self.filter_options(queryset)
        return queryset

    def update_session(self):
        """
        Serializes the cart data, saves it to session and marks session as modified.
        """
        self.session[self.session_key] = self.cart_serializable
        self.session.modified = True

    def add(self, product, options=[], quantity=1):
        """
        Adds or creates products in cart. For an existing product,
        the quantity is increased and the price is ignored.
        """
        quantity = int(quantity)
        if quantity < 1:
            raise ValueError('Quantity must be at least 1 when adding to cart')
        item_index = self.__index__(product, options)
        if item_index != -1:
            self._items_dict[item_index].quantity += quantity
        else:
            self._items_dict.append(CartItem(product, options, quantity))
        self.update_session()

    def remove(self, product):
        """
        Removes the product.
        """
        item_index = self.__index__(product, options)
        if item_index != -1:
            del self._items_dict[item_index]
            self.update_session()

    def remove_single(self, product):
        """
        Removes a single product by decreasing the quantity.
        """
        item_index = self.__index__(product, options)
        if item_index != -1:
            if self._items_dict[item_index].quantity <= 1:
                del self._items_dict[item_index]
            else:
                self._items_dict[item_index].quantity -= 1
            self.update_session()

    def clear(self):
        """
        Removes all items.
        """
        self._items_dict = []
        self.update_session()

    def set_quantity(self, product, quantity, options=[]):
        """
        Sets the product's quantity.
        """
        quantity = int(quantity)
        if quantity < 0:
            raise ValueError('Quantity must be positive when updating cart')
        item_index = self.__index__(product, options)
        if item_index != -1:
            self._items_dict[item_index].quantity = quantity
            if self._items_dict[item_index].quantity < 1:
                del self._items_dict[item_index]
            self.update_session()

    @property
    def items(self):
        """
        The list of cart items.
        """
        return self._items_dict

    @property
    def cart_serializable(self):
        """
        The serializable representation of the cart.
        """
        return [item.to_dict() for item in self.items]


    # @property
    # def items_serializable(self):
    #     """
    #     The list of items formatted for serialization.
    #     """
    #     return self.cart_serializable.items()

    @property
    def count(self):
        """
        The number of items in cart, that's the sum of quantities.
        """
        return sum([item.quantity for item in self.items])

    @property
    def unique_count(self):
        """
        The number of unique items in cart, regardless of the quantity.
        """
        return len(self._items_dict)

    @property
    def is_empty(self):
        return self.unique_count == 0

    @property
    def products(self):
        """
        The list of associated products.
        """
        return list(set([item.product for item in self.items]))

    @property
    def total(self):
        """
        The total value of all items in the cart.
        """
        return sum([item.subtotal for item in self.items])
