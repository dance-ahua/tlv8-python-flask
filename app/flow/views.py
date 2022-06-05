# _*_ coding: utf-8 _*_

from . import flow
from flask import request, render_template, url_for, redirect, session, send_file
from app import db
from app.models import SATask
from app.common.decorated import user_login
from app.common.pubstatic import url_decode, create_icon
from app.common.persons import get_curr_person_info, get_person_list_by_org
from app.flow.flowcontroller import start_flow, out_flow
from app.flow.flowentity import FlowActivity
from app.flow.expprocess import *
from app.flow.exporgexecutor import *
from app.common.persons import *
from datetime import datetime
import json


# 打开待办
@flow.route("/openTaskAction", methods=["GET", "POST"])
@user_login
def open_task_action():
    rdata = dict()
    person = get_curr_person_info()
    taskID = url_decode(request.form.get('taskID', ''))
    executor = url_decode(request.form.get('executor', ''))
    if not executor or executor == "" or executor == "null":
        executor = person['personid']
    task = SATask.query.filter_by(sid=taskID, sepersonid=executor).first()
    if task:
        task.slock = person['personid']
        db.session.add(task)
        processID = task.sprocess
        activity = task.sactivity
        Act = FlowActivity(processID, activity)
        if Act.getGrapModle() == "whenOpen":  # 打开时抢占，则自动取消当前环节其他待办
            upsql = ("update SA_TASK set SSTATUSID='tesCanceled' ,SSTATUSNAME='已取消' "
                     " where SID != :taskID and SACTIVITY = :activity and SFLOWID = :flowID and SSTATUSID = 'tesReady'")
            db.session.execute(upsql, {'taskID': taskID, 'activity': activity, 'flowID': task.sflowid})
        db.session.commit()
        data = dict()
        data['taskID'] = task.sid
        data['flowID'] = task.sflowid
        data['name'] = task.sname
        data['url'] = task.seurl
        data['sData1'] = task.sdata1
        rdata['data'] = data
        rdata['state'] = True
    else:
        rdata['state'] = False
        rdata['msg'] = "ID为'" + taskID + "'的任务不存在或您没有权限处理!"
    return json.dumps(rdata, ensure_ascii=False)


# 启动流程
@flow.route("/flowStartAction", methods=["GET", "POST"])
@user_login
def flow_start_action():
    rdata = dict()
    try:
        sdata1 = url_decode(request.form.get('sdata1', ''))
        srcPath = url_decode(request.form.get('srcPath', ''))
        processID = url_decode(request.form.get('processID', None))
        process_id, flowID, taskID, afactivity = start_flow(sdata1, srcPath, processID)
        ePersonList = list()
        ePersonList.append(get_curr_person_info())
        taskIDs = out_flow(flowID, taskID, sdata1, ePersonList, afactivity)
        data = dict()
        data['processID'] = process_id
        data['flowID'] = flowID
        data['taskID'] = taskIDs[0]
        rdata['data'] = data
        rdata['state'] = True
    except Exception as e:
        rdata['state'] = False
        rdata['msg'] = str(e)
    return json.dumps(rdata, ensure_ascii=False)


# 流程流转（提交）
@flow.route("/flowOutAction", methods=["GET", "POST"])
@user_login
def flow_out_action():
    rdata = dict()
    flowID = url_decode(request.form.get('flowID', ''))
    taskID = url_decode(request.form.get('taskID', ''))
    sdata1 = url_decode(request.form.get('sdata1', ''))
    epersonids = url_decode(request.form.get('epersonids'))
    afterActivity = url_decode(request.form.get('afterActivity'))
    task = SATask.query.filter_by(sid=taskID, sstatusid='tesReady').first()
    if task:
        processID = task.sprocess
        Activity = task.sactivity
        if task.skindid == "note":  # 如果待办为‘通知’类型则直接完成不做其他处理
            task.sexecutetime = datetime.now()
            task.sstatusid = 'tesFinished'
            task.sstatusname = '已完成'
            task.version = task.version + 1
            db.session.add(task)
            db.session.commit()
            rdata['state'] = True
            data = dict()
            data['processID'] = processID
            data['flowID'] = flowID
            data['taskID'] = taskID
            rdata['data'] = data
            return json.dumps(rdata, ensure_ascii=False)
        flwA = FlowActivity(processID, Activity)
        if flwA.getGrapModle() == "together" and flwA.getGrapWay() == "merge":  # 当前环节为“共同模式”则需要判断是否所有人已处理任务
            ch_task = SATask.query.filter(SATask.sflowid == task.sflowid, SATask.sactivity == flwA.getActivity(),
                                          SATask.sid != taskID, SATask.sstatusid == 'tesReady').first()
            if ch_task:  # 如果有其他待办则值更新状态并提示“等待其他人处理”
                task.sexecutetime = datetime.now()
                task.sstatusid = 'tesFinished'
                task.sstatusname = '已完成'
                task.version = task.version + 1
                db.session.add(task)
                db.session.commit()
                rdata['state'] = 'msg'
                rdata['msg'] = '请等待其他人处理!'
                return json.dumps(rdata, ensure_ascii=False)
        aftAList = list()
        if afterActivity and afterActivity != "":  # 如果指定了环节则不需要选择确认
            if epersonids and epersonids != "":  # 如果已经选择执行人则直接流转
                ePersonList = get_person_list_by_org(epersonids)
                taskIDs = out_flow(flowID, taskID, sdata1, ePersonList, afterActivity)
                if taskIDs:
                    rdata['state'] = True
                    data = dict()
                    data['processID'] = processID
                    data['flowID'] = flowID
                    data['taskID'] = taskIDs[0]
                    rdata['data'] = data
                    return json.dumps(rdata, ensure_ascii=False)
            aftAList.append(FlowActivity(processID, afterActivity))
        else:
            aftAList = flwA.getAfterActivity()
        if len(aftAList) == 1:
            # 下一环节为“结束环节”且当前环节不是“共同模式”则直接结束流程
            if aftAList[0].getType() == "end" and (flwA.getGrapModle() != "together" or flwA.getGrapWay() != "merge"):
                newtaskIDs = out_flow(flowID, taskID, sdata1, None, aftAList[0].getActivity())
                data = dict()
                data['processID'] = processID
                data['flowID'] = flowID
                data['taskID'] = newtaskIDs[0]
                rdata['data'] = data
                rdata['state'] = 'end'
                return json.dumps(rdata, ensure_ascii=False)
            if aftAList[0].getOutquery() == "no":  # 不需要流转确认时处理
                epersonid = aftAList.get(0).getExcutorIDs()
                ePersonList = list()
                if epersonid and epersonid != "":
                    ePersonList = get_person_list_by_org(epersonid)
                else:
                    exeGroup = aftAList[0].getExcutorGroup()
                    if exeGroup and exeGroup != "":  # 配置了执行规则的“群组”则解析表达式获得执行人信息
                        exeGroup = exeGroup.replace("getProcessID()", processID)
                        exeGroup = exeGroup.replace("getFlowID()", flowID)
                        exeGroup = exeGroup.replace("getTaskID()", taskID)
                        exeGroup = exeGroup.replace("getProcesssData1()", sdata1)
                        excutorGroup = eval(exeGroup)
                    else:  # 如果没有配置规则则自动获取有权限的人员
                        exeGroup = "get_org_unit_has_activity('" + processID + "','" + aftAList[
                            0].getActivity() + "',False,False)"
                        excutorGroup = eval(exeGroup)
                    ePersonList = get_person_list_by_org(excutorGroup)
                if len(ePersonList) > 0:
                    taskIDs = out_flow(flowID, taskID, sdata1, ePersonList, aftAList[0].getActivity())
                    if taskIDs:
                        rdata['state'] = True
                        rdata['processID'] = processID
                        rdata['flowID'] = flowID
                        rdata['taskID'] = taskIDs.split(",")[0]
                        return json.dumps(rdata, ensure_ascii=False)
        afterActList = list()
        for afactivity in aftAList:
            nactivity = dict()
            nactivity['id'] = afactivity.getId()
            nactivity['name'] = afactivity.getActivityname()
            nactivity['type'] = afactivity.getType()
            nactivity['excutorIDs'] = afactivity.getExcutorIDs()
            nactivity['excutorNames'] = afactivity.getExcutorNames()
            exeGroup = afactivity.getExcutorGroup()
            if exeGroup and exeGroup != "":
                exeGroup = exeGroup.replace("getProcessID()", processID)
                exeGroup = exeGroup.replace("getFlowID()", flowID)
                exeGroup = exeGroup.replace("getTaskID()", taskID)
                exeGroup = exeGroup.replace("getProcesssData1()", sdata1)
                excutorGroup = eval(exeGroup)
            else:  # 如果没有配置规则则自动获取有权限的人员
                exeGroup = "get_org_unit_has_activity('" + processID + "','" + aftAList[
                    0].getActivity() + "',False,False)"
                excutorGroup = eval(exeGroup)
            nactivity['excutorGroup'] = excutorGroup
            activitylabel = afactivity.getsActivityLabel()
            if not activitylabel or activitylabel == "":
                activitylabel = afactivity.getActivityname() + ":" + afactivity.getProcessName()
            else:
                activitylabel = activitylabel.replace("getProcessID()", processID)
                activitylabel = activitylabel.replace("getFlowID()", flowID)
                activitylabel = activitylabel.replace("getTaskID()", taskID)
                activitylabel = activitylabel.replace("getProcesssData1()", sdata1)
                activitylabel = eval(activitylabel)
            nactivity['label'] = activitylabel
            afterActList.append(nactivity)
        rdata['state'] = 'select'
        data = dict()
        data['processID'] = processID
        data['flowID'] = flowID
        data['taskID'] = taskID
        data['activityList'] = afterActList
        rdata['data'] = data
    else:
        rdata['state'] = False
        rdata['msg'] = "任务id无效,或任务已经处理完成不能再处理！"
    return json.dumps(rdata, ensure_ascii=False)


# 加载流程执行人
@flow.route("/getExecutorTree", methods=["GET", "POST"])
@user_login
def flow_get_executor_tree():
    rdata = dict()
    exGroup = url_decode(request.form.get('exGroup', ''))
    excutorIDs = url_decode(request.form.get('excutorIDs', ''))
    isflowMonitor = url_decode(request.form.get('isflowMonitor'))
    sql = ("select distinct a.sparent,a.sid,a.scode,a.sname,a.sfid,a.sorgkindid,a.ssequence,a.slevel from "
           " sa_oporg a inner join (select sfid from sa_oporg where svalidstate=1 ")
    if exGroup and exGroup != "":
        sql += " and (1=2 "
        for sid in exGroup.split(","):
            sql += " or sfid like '%" + sid + "%' "
        if excutorIDs and excutorIDs != "":
            for sid in excutorIDs.split(","):
                sql += " or sfid like '%" + sid + "%' "
        sql += ")"
    sql += ")b on b.sfid like concat(a.sfid,'%') where a.svalidstate=1 order by a.slevel asc,a.ssequence asc"
    org_list = db.session.execute(sql)
    data_list = list()
    for org in org_list:
        data = dict()
        data['id'] = org.sid
        data['name'] = org.sname
        data['type'] = org.sorgkindid
        data['icon'] = create_icon(org.sorgkindid)
        data['pId'] = org.sparent
        if org.sorgkindid != "psm":
            data["open"] = "true"
        data_list.append(data)
    rdata['state'] = True
    rdata['data'] = data_list
    return json.dumps(rdata, ensure_ascii=False)


# 加载波特图
@flow.route("/flowloadbotAction", methods=["GET", "POST"])
@user_login
def flow_load_bot_action():
    rdata = dict()
    flowID = url_decode(request.form.get('flowID', ''))
    task_list = SATask.query.filter(SATask.sstatusid != 'tesExecuting', SATask.sactivity is not None,
                                    SATask.sflowid == flowID).order_by(SATask.screatetime.asc()).all()
    bot_list = list()
    for task in task_list:
        botdata = dict()
        botdata['id'] = task.sid
        botdata['title'] = task.sname
        botdata['executor'] = task.sepersonname
        botdata['excutordpt'] = task.sedeptname
        botdata['status'] = task.sstatusname
        botdata['creator'] = task.scpersonname
        botdata['createTime'] = datetime.strftime(task.screatetime, '%Y-%m-%d %H:%M:%S')
        if task.sexecutetime:
            botdata['auditeTime'] = datetime.strftime(task.sexecutetime, '%Y-%m-%d %H:%M:%S')
        else:
            botdata['auditeTime'] = ''
        botdata['activity'] = task.sactivity
        bot_list.append(botdata)
    rdata['state'] = True
    rdata['data'] = bot_list
    return json.dumps(rdata, ensure_ascii=False)


# 加载波特图X
@flow.route("/flowloadbotXAction", methods=["GET", "POST"])
@user_login
def flow_load_botx_action():
    rdata = dict()
    flowID = url_decode(request.form.get('flowID', ''))
    task_list = SATask.query.filter(SATask.sstatusid != 'tesExecuting', SATask.sactivity is not None,
                                    SATask.sflowid == flowID).order_by(SATask.screatetime.asc()).all()
    bot_list = list()
    for task in task_list:
        botdata = dict()
        botdata['id'] = task.sid
        botdata['name'] = task.sname
        botdata['executor'] = task.sepersonname
        botdata['executordepartment'] = task.sedeptname
        botdata['status'] = task.sstatusname
        botdata['creator'] = task.scpersonname
        botdata['createtime'] = datetime.strftime(task.screatetime, '%Y-%m-%d %H:%M:%S')
        if task.sexecutetime:
            botdata['executetime'] = datetime.strftime(task.sexecutetime, '%Y-%m-%d %H:%M:%S')
        else:
            botdata['executetime'] = ''
            botdata['activity'] = task.sactivity
        if task.sparentid and flowID != task.sparentid:
            ahead = list()
            ahead.append(task.sparentid)
            botdata['ahead'] = ahead
        anext = list()
        child = SATask.query.filter_by(sparentid=task.sid).all()
        for c in child:
            anext.append(c.sid)
        botdata['next'] = anext
        bot_list.append(botdata)
    rdata['state'] = True
    rdata['data'] = bot_list
    return json.dumps(rdata, ensure_ascii=False)


# 检查流程是否已结束
@flow.route("/flowcheckfinishAction", methods=["GET", "POST"])
@user_login
def flow_check_finish_action():
    rdata = dict()
    try:
        flowID = url_decode(request.form.get('flowID', ''))
        task = SATask.query.filter_by(sid=flowID, sstatusid='tesFinished').first()
        if task:
            rdata['data'] = True
        else:
            rdata['data'] = False
        rdata['state'] = True
    except Exception as e:
        rdata['state'] = False
        rdata['msg'] = str(e)
    return json.dumps(rdata, ensure_ascii=False)
