from django.conf.urls import url

from . import views
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

urlpatterns = [
    url(r'^profile/contract/[0-9]+/delete$', views.delete_contract, name='contract delete'),
    url(r'^profile/contract/add/$', views.contractAdd, name='contractAdd'),
    url(r'^profile/$', views.profile, name='profile'),
    url(r'^profile/delete$', views.delete_profile, name='delete profile'),
    url(r'^$', views.index, name='index'),
    url(r'^faq/$', views.faq, name='faq'),
    url(r'^contract/[0-9]+/10|11|12|[1-9]/[0-9]{4}/print/$', views.printView, name='faq'),
]
