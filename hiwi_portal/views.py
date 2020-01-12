# -*- coding: utf-8 -*-
from django.shortcuts import render
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from models import Contract, WorkLog, WorkTime, FillerWorkDustActivity, FixedWorkDustActivity
from datetime import datetime, timedelta
from calendar import monthrange
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import redirect
import tempfile
import shutil
import configparser
import time
import re
import math
from django.db.models import Max
from django.contrib.auth import logout
from subprocess import Popen
from django.db.models import Min

FORM = ""


def getWorkLog(contract, month, year):
    try:
        if contract.contract_begin.year > year or \
                        contract.contract_end.year < year or \
                (contract.contract_begin.year == year and contract.contract_begin.month > month) or \
                (contract.contract_end.year == year and contract.contract_end.month < month):
            raise ValidationError("Invalid workLog (shouldn't happen)")
        workL = WorkLog.objects.get(contract=contract, month=month, year=year)
    except ObjectDoesNotExist:
        workL = WorkLog()
        workL.month = month
        workL.year = year
        workL.contract = contract
        workL.save()
    return workL


def getNextWorkLog(contract, month, year):
    nextMonth = month + 1
    nextYear = year
    if nextMonth > 12:
        nextMonth = 1
        nextYear += 1
    return getWorkLog(contract, nextMonth, nextYear)


def getMilogPath():
    global FORM
    if FORM:
        return FORM
    config = configparser.ConfigParser()
    config.read("config.ini")
    try:
        FORM = config.get("formgen", "milog_path")
        return FORM
    except configparser.NoOptionError as e:
        print ("Missing configuartion! ", e)
        exit(1)


@login_required
def index(request):
    user = request.user
    context = {"user": user}
    contracts = user.contract_set.all()
    now = datetime.now()
    month = now.month
    year = now.year
    context['year'] = year
    context['month'] = month
    if request.method == 'GET':
        if request.GET.get('month') and request.GET.get('year'):
            if int(request.GET['month']) > 12 or int(request.GET['month']) < 1:
                raise ValidationError("Invalid month.")
            if int(request.GET['year']) > year + 2 or int(request.GET['year']) < year - 2:
                raise ValidationError("Invalid year.")
            month = int(request.GET['month'])
            year = int(request.GET['year'])
            context['year'] = year
            context['month'] = month
    if request.method == 'POST':
        if request.POST.get('month') and request.POST.get('year'):
            if int(request.POST['month']) > 12 or int(request.POST['month']) < 1:
                raise ValidationError("Invalid month.")
            if int(request.POST['year']) > year + 2 or int(request.POST['year']) < year - 2:
                raise ValidationError("Invalid year.")
            month = int(request.POST['month'])
            year = int(request.POST['year'])
            context['year'] = year
            context['month'] = month
        if request.POST.get("contract_id"):
            try:
                contract = Contract.objects.get(id=request.POST["contract_id"])
                wt = WorkTime()
                wt.activity = request.POST['activity']
                wt.pause = request.POST['pause']
                if not wt.pause:
                    wt.pause = 0
                start = request.POST['date'] + " " + request.POST['start']
                startpattern = "%Y-%m-%d %H:%M"
                if re.match(r'^([0-9]{2}|[0-9])$', request.POST['start']):
                    startpattern = "%Y-%m-%d %H"
                start = datetime.strptime(start, startpattern)
                endpattern = "%Y-%m-%d %H:%M"
                if re.match(r'^([0-9]{2}|[0-9])$', request.POST['end']):
                    endpattern = "%Y-%m-%d %H"
                end = request.POST['date'] + " " + request.POST['end']
                end = datetime.strptime(end, endpattern)
                year = start.year
                month = start.month
                wLog = WorkLog.objects.get(contract=contract, month=month, year=year)
                wt.work_log = wLog
                wt.end = end
                wt.begin = start
                wt.clean_fields(year, month)
                wt.save()
            except ObjectDoesNotExist as v:
                context['error'] = [v.message]
            except ValueError as v:
                context['error'] = [v.message]
            except ValidationError as v:
                context['error'] = v.messages
            context['post'] = 'y'
            context['posted_contract'] = int(request.POST['contract_id'])
            context['postdata'] = request.POST
    month = context['month']
    year = context['year']
    ctracs = []
    for c in contracts:
        if c.contract_begin.year > year or \
                        c.contract_end.year < year or \
                (c.contract_begin.year == year and c.contract_begin.month > month) or \
                (c.contract_end.year == year and c.contract_end.month < month):
            continue

        workL = getWorkLog(c, month, year)
        workSum = workL.calcHours()
        c.cw = workL
        c.cSum = workSum
        c.percent = (workSum/c.hours)*100.0
        c.partVac = int(round(workL.contract.vacation / 12.0))
        if c.hours * 1.5 - workSum <= c.hours * 1.5 - c.hours:
            c.critSum = True
        ctracs.append(c)
    context['contracts'] = ctracs
    years = []
    for i in range(-2, 3):
        years.append(datetime.now().year + i)
    context['years'] = years
    return render(request, 'hiwi_portal.html', context)


@login_required
def profile(request):
    user = request.user
    context = {"user": user}
    try:
        if request.method == 'POST':
            if not request.POST["data"] == None:
                user.phone_number = request.POST['phone']
                user.private_email = request.POST['private_email']
                user.clean_fields()
                if 'private_notif' in request.POST:
                    if not request.POST['private_email']:
                        raise ValidationError(
                            "A private E-Mail adress is required to get notified to your private E-Mail adress.")
                    user.notify_to_private = True
                else:
                    user.notify_to_private = False
                user.save()
            context['post'] = 'y'
    except ValidationError as v:
        context['error'] = v.messages
    return render(request, 'profile.html', context)


def faq(request):
    return render(request, 'faq.html', {})


@login_required
def contractAdd(request):
    user = request.user
    context = {"user": user}
    try:
        if request.method == 'POST':
            context['post'] = 'y'
            contract = Contract()
            contract.department = request.POST['institute']
            contract.user = user
            contract.personell_number = request.POST['personell_id']
            cStart = request.POST['contract_start']
            cEnd = request.POST['contract_end']
            cStart = datetime.strptime(cStart, "%Y-%m-%d")
            cEnd = datetime.strptime(cEnd, "%Y-%m-%d")
            contract.contract_begin = cStart
            contract.contract_end = cEnd
            contract.personell = request.POST['dp']
            contract.hours = request.POST['work_hours']
            contract.payment = request.POST['payment']
            contract.vacation = round((int(contract.hours) * 20 * 3.95) / 85.0)
            contract.clean_fields()
            contract.save()
            return redirect("/profile")

    except ValidationError as v:
        context['error'] = v.messages
        print(v)
    except ValueError as v:
        context['error'] = [v.message]
    context['postdata'] = request.POST
    return render(request, 'contract_add.html', context)


def tex_escape(tex):
    tex = tex.replace('&', '\&')
    tex = tex.replace('\\', '\\textbackslash')
    tex = tex.replace('~', '\\textasciitilde')
    return tex

@login_required
def printView(request, contract, month, year):
    user = request.user
    contract = Contract.objects.get(id=int(contract), user=user)
    workL = WorkLog.objects.get(month=int(month), year=int(year), contract=contract)
    response = HttpResponse(content_type='application/pdf')

    out = tempfile.mkdtemp()
    templ = open(getMilogPath() + "/milog_form_placehold.tex", "r")
    templEnd = open(out + '/h.tex', "w+")
    templR = templ.read().decode("utf-8")
    templ.close()
    templR = templR.replace("{!name}", tex.escape(user.lastname) + ", " + tex.escape(user.firstname))
    templR = templR.replace("{!personell_number}", str(contract.personell_number))
    if (contract.personell == "UB"):
        templR = templR.replace("{!gf}", "")
        templR = templR.replace("{!ub}", "checked,")
    else:
        templR = templR.replace("{!gf}", "checked,")
        templR = templR.replace("{!ub}", "")
    templR = templR.replace("{!contract_hours}", str(contract.hours))
    templR = templR.replace("{!contract_pay}", str(contract.payment))
    templR = templR.replace("{!my}", month + "/" + year)
    rows = ""
    for t in workL.worktime_set.all().order_by("begin"):
        rows += "%s & %s & %s & %s & %s & %.2f\\\\ \hline\n" % (tex_escape(t.activity),
                                                                t.begin.strftime("%d.%m.%y"),
                                                                t.begin.strftime("%H:%M"),
                                                                t.end.strftime("%H:%M"),
                                                                str(t.pause) + ":00",
                                                                t.hours())
    endSum = workL.calcHours(False)
    templR = templR.replace("{!rows}", rows)
    templR = templR.replace("{!sum}", str(float(endSum)))
    templR = templR.replace("{!overwork}", str(workL.calc_over_work()))
    templR = templR.replace("{!vacation}", str(int(round(workL.contract.vacation / 12.0))))
    overNext = workL.calcHours() - contract.hours
    templR = templR.replace("{!overworknext}", str(float(overNext)))
    templEnd.write(templR.encode("utf-8"))
    templEnd.close()
    p = Popen(['pdflatex', '-output-directory=' + out, out + '/h.tex', '-interaction nonstopmode', '-halt-on-error',
               '-file-line-error'], cwd=getMilogPath())
    p.wait()
    f = open(out + '/h.pdf', 'r')
    response.write(f.read())
    f.close()
    shutil.rmtree(out)
    return response


@login_required
def delete_profile(request):
    if request.method == 'POST':
        user = request.user
        user.delete()
        return redirect("/logout")
    return redirect("/profile")


@login_required
def delete_contract(request):
    contr = Contract(user=request.user, id=int(request.path_info.split("/")[3]))
    contr.delete()
    return redirect("/profile/")


@login_required
def delete_work(request):
    wt = WorkTime.objects.get(id=int(request.path_info.split("/")[2]))
    if wt.work_log.contract.user == request.user:
        cid = str(wt.work_log.contract.id)
        month = str(wt.work_log.month)
        year = str(wt.work_log.year)
        wt.delete()
    return redirect("/?month=" + month + "&year=" + year + "#" + cid)


@login_required
def work_dust(request):
    user = request.user
    user.work_dusted = True
    user.save()
    return redirect("/")


@login_required
def wd_manage_fill(request):
    user = request.user
    c = Contract.objects.get(id=int(request.POST['contract']), user=user)
    f = FillerWorkDustActivity()
    f.contract = c
    f.description = request.POST['description']
    f.avg_length = request.POST['dur']
    f.clean_fields()
    f.save()
    return redirect("/profile#wd")


@login_required
def wd_manage_anual(request):
    user = request.user
    c = Contract.objects.get(id=int(request.POST['contract']), user=user)
    f = FixedWorkDustActivity()
    start = request.POST['start']
    f.start = datetime.strptime(start, "%H:%M")
    f.contract = c
    f.week_day = request.POST['weekday']
    f.description = request.POST['description']
    f.avg_length = request.POST['dur']
    f.clean_fields()
    f.save()
    return redirect("/profile#wd")


@login_required
def wd_delete_anual(request, id):
    user = request.user
    a = FixedWorkDustActivity.objects.get(id=id)
    if a.contract.user == user:
        a.delete()
    return redirect("/profile#wd")


@login_required
def wd_delete_filler(request, id):
    user = request.user
    a = FillerWorkDustActivity.objects.get(id=id)
    if a.contract.user == user:
        a.delete()
    return redirect("/profile#wd")


@login_required
def wd_manage_apply(request, month, year, contract):
    c = Contract.objects.get(id=int(contract), user=request.user)
    month = int(month)
    year = int(year)
    firstDayOfMonth = datetime(year, month, 1, 0, 0, 1, 0).weekday()
    daysInMonth = monthrange(year, month)
    workL = WorkLog.objects.get(contract=c, month=month, year=year)
    # First try apply all anual activities
    anuals = c.fixedworkdustactivity_set.all()
    for a in anuals:
        if a.week_day > firstDayOfMonth:
            anualStep = 1 + a.week_day - firstDayOfMonth
        elif a.week_day == firstDayOfMonth:
            anualStep = 1
        else:
            anualStep = 1 + 7 - firstDayOfMonth + a.week_day
        while anualStep <= daysInMonth[1] and workL.calcHours() + a.avg_length <= c.hours:
            wt = WorkTime()
            wt.work_log = workL
            if a.avg_length >= 6:
                wt.pause = 1
            else:
                wt.pause = 0
            wt.begin = datetime(year, month, anualStep, a.start.hour, a.start.minute, 0, 0)
            beginstamp = (wt.begin - datetime(1970, 1, 1)).total_seconds()
            wt.end = datetime.fromtimestamp(beginstamp +
                                            a.avg_length * 60.0*60.0 + wt.pause * 60.0*60.0)
            # wt.end = wt.begin.replace(hour=int(wt.begin.hour + math.floor(a.avg_length) + wt.pause))
            # wt.end = wt.end.replace(minute=int(round((a.avg_length - math.floor(a.avg_length)) * 60)))
            wt.activity = a.description
            wt.clean_fields(year, month)
            wt.save()
            anualStep += 7
    # Then fill with "other" activities
    filler = FillerWorkDustActivity.objects.all()
    largestFreeSlot = 0
    smallestFiller = filler.aggregate(Min('avg_length'))['avg_length__min']

    while not smallestFiller == None and largestFreeSlot >= smallestFiller:
        pass
    return redirect("/?month=" + str(month) + "&year=" + str(year) + "#" + str(c.id))
