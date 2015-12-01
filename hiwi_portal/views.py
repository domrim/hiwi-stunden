# -*- coding: utf-8 -*-
from django.shortcuts import render
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from models import Contract, WorkLog, WorkTime
from datetime import datetime
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import redirect
import tempfile
import shutil
import time
from django.contrib.auth import logout
from subprocess import Popen

#TODO: In ordentlich im model
def calcHours(worklog):
    workSum = 0
    logs = worklog.worktime_set.all()
    for l in logs:
        workSum += l.hours
    return workSum

@login_required
def index(request):
    user = request.user
    context = {"user":user}
    contracts = user.contract_set.all()
    now = datetime.now()
    month = now.month
    year = now.year
    context['year'] = year
    context['month'] = month
    if request.method == 'POST':
        if request.POST.get('month') and request.POST.get('year'):
            if int(request.POST['month']) > 12 or int(request.POST['month']) < 1:
                raise ValidationError("Invalid month.")
            if int(request.POST['year']) > year+2 or int(request.POST['year']) < year-2:
                raise ValidationError("Invalid year.")
            month = int(request.POST['month'])
            year = int(request.POST['year'])
            context['year'] = year
            context['month'] = month
        if request.POST.get("contract-id"):
            try:
                contract = Contract.objects.get(id=request.POST["contract-id"])
                wLog = WorkLog.objects.get(contract=contract, month=month, year=year)
                wt = WorkTime()
                wt.work_log = wLog
                wt.activity = request.POST['activity']
                #wt.hours = request.POST['work']
                wt.pause = request.POST['pause']
                if not wt.pause:
                    wt.pause = 0
                date = request.POST['date']
                end = request.POST['end']
                start = request.POST['start']
                start = datetime.strptime(start, "%H:%M")
                end = datetime.strptime(end, "%H:%M")
                startStamp = time.mktime(start.timetuple())
                endStamp = time.mktime(end.timetuple())
                if start.hour < 6 or end.hour > 20 or (end.hour==20 and end.minute > 0):
                    raise ValidationError("You can only work at daytime. Sorry coffee nerds ;(")
                if startStamp >= endStamp:
                    raise ValidationError("The start time have to be before the end time.")
                if (int(wt.pause)*60*60) >= endStamp-startStamp:
                    raise ValidationError("Such error, many pause!")
                wt.hours = round(((endStamp-startStamp)-int(wt.pause)*60*60)/60/60)
                if(wt.hours == 0):
                    raise ValidationError("Worktime caped to 0.")
                if calcHours(wLog)+wt.hours > contract.hours:
                    raise ValidationError("Max. monthly worktime exceeded!")
                date = datetime.strptime(date, "%Y-%m-%d")
                wt.end = end
                wt.begin = start
                wt.date = date
                wt.clean_fields()
                wt.save()
            except ObjectDoesNotExist as v:
                context['error'] = [v.message]
            except ValueError as v:
                context['error'] = [v.message]
            except ValidationError as v:
                context['error'] = v.messages
            context['post'] = 'y'
    ctracs = []
    for c in contracts:
        if c.contract_begin.year > year or \
        c.contract_end.year < year or \
        (c.contract_begin.year == year and c.contract_begin.month > month) or \
        (c.contract_end.year == year and c.contract_end.month < month):
            continue

        workSum = 0
        try:
            workL = WorkLog.objects.get(contract=c, month=month, year=year)
            workSum = calcHours(workL)
        except ObjectDoesNotExist:
            workL = WorkLog()
            workL.month = month
            workL.year = year
            workL.contract = c
            workL.save()
        c.cw=workL
        c.cSum = workSum
        if c.hours-workSum < 6:
            c.critSum = True
        ctracs.append(c)
    context['contracts'] = ctracs
    years = []
    for i in range(-2, 3):
        years.append(datetime.now().year+i)
    context['years'] = years
    return render(request, 'hiwi_portal.html', context)


@login_required
def profile(request):
    user = request.user
    context = {"user":user}
    try:
        if request.method == 'POST':
            if not request.POST["data"] == None:
                    user.phone_number = request.POST['phone']
                    user.private_email = request.POST['private_email']
                    user.clean_fields()
                    if 'private_notif' in request.POST:
                        if not request.POST['private_email']:
                            raise ValidationError("A private E-Mail adress is required to get notified to your private E-Mail adress.")
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
    context = {"user":user}
    try:
        if request.method == 'POST':
            context['post'] = 'y'
            contract = Contract()
            contract.department = request.POST['institute']
            contract.user = user
            contract.personell_number = request.POST['personell-id']
            cStart = request.POST['contract-start']
            cEnd = request.POST['contract-end']
            cStart = datetime.strptime(cStart, "%Y-%m-%d")
            cEnd = datetime.strptime(cEnd, "%Y-%m-%d")
            contract.contract_begin = cStart
            contract.contract_end = cEnd
            contract.personell = request.POST['dp']
            contract.hours = request.POST['work-hours']
            contract.payment = request.POST['payment']
            contract.vacation = round((int(contract.hours) *20*3.95)/85.0)
            contract.clean_fields()
            contract.save()
            return redirect("/profile")

    except ValidationError as v:
        context['error'] = v.messages
        print(v)
    except ValueError as v:
        context['error'] = [v.message]
    return render(request, 'contract_add.html', context)

@login_required
def printView(request):
    user = request.user
    pathComp = request.path_info.split("/")
    contract = Contract.objects.get(id=int(pathComp[2]), user=user)
    workL = WorkLog.objects.get(month=int(pathComp[3]),year=int(pathComp[4]), contract=contract)
    response = HttpResponse(content_type='application/pdf')

    out = tempfile.mkdtemp()
    templ = open("milog-form/milog_form_placehold.tex", "r")
    templEnd = open(out+'/h.tex', "w+")
    templR = templ.read().decode("utf-8")
    templ.close()
    templR = templR.replace("{!name}", user.lastname +", "+user.firstname)
    templR = templR.replace("{!personell_number}", str(contract.personell_number))
    if(contract.personell == "UB"):
        templR = templR.replace("{!gf}", "")
        templR = templR.replace("{!ub}", "checked,")
    else:
        templR = templR.replace("{!gf}", "checked,")
        templR = templR.replace("{!ub}", "")
    templR = templR.replace("{!contract_hours}", str(contract.hours))
    templR = templR.replace("{!contract_pay}", str(contract.payment))
    templR = templR.replace("{!my}", pathComp[3]+"/"+pathComp[4])
    rows = ""
    endSum = 0
    for t in  workL.worktime_set.all():
        rows += "%s & %s & %s & %s & %s & %d\\\\ \hline\n" % (t.activity,
            t.date.strftime("%d.%m.%y") ,
            t.begin.strftime("%H:%M"),
            t.end.strftime("%H:%M"),
            str(t.pause)+":00",
            t.hours)
        endSum += t.hours
    templR = templR.replace("{!rows}", rows)
    templR = templR.replace("{!sum}", str(endSum))
    templEnd.write(templR.encode("utf-8"))
    templEnd.close()
    p = Popen(['pdflatex', '-output-directory='+out, out+'/h.tex', '-interaction nonstopmode', '-halt-on-error', '-file-line-error'], cwd='milog-form/')
    p.wait()
    f = open(out+'/h.pdf', 'r')
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
