var currenttreeID = null, currentNode;

/* =========创建树========== */

var param = {
    cell: {
        id: "sid",// 设置构建树的id
        name: "sname",// 树显示的名称
        parent: "sparent",// 表示树的层级
        other: "sfid,sfname,sorgkindid,scode,sfcode"// 树中所带字段信息
    }
};
var setting = {
    view: {
        selectedMulti: false, // 设置是否允许同时选中多个节点。默认值: true
        autoCancelSelected: false,
        dblClickExpand: true
        // 双击展开
    },
    data: {
        simpleData: {
            enable: true
        }
    },
    async: {
        enable: true, // 异步加载
        url: "/system/OPM/TreeSelectAction",// 加载数据的Action,可以自定义
        autoParam: ["id=currenid"]
    },
    isquickPosition: {
        enable: true, // 是否有快速查询框
        url: "/system/OPM/QuickTreeAction",
        quickCells: "sid,scode,sname",// 用于快速查询的字段
        path: "sfid"// 查询路径字段
    },
    callback: {
        beforeClick: beforeClick,
        afterRefresh: afterRefresh
    }
};


function afterRefresh(event) {
    currentNode = null;
    currenttreeID = null;
    loadList();
}

function beforeClick(treeId, treeNode) {
    currentNode = treeNode;
    currenttreeID = treeNode.id;
    loadList();
}

var MainJtree = new Jtree();

function pageLoad() {
    MainJtree.init("JtreeView", setting, param);
}

function loadList() {
    layui.table.reload("psmlist", {
        url: "/system/OPM/psmList?spfid=" + (currentNode ? currentNode.sfid : "")
    })
}

var checkData = new Map();

function gridChecked(data, checked) {
    if (checked) {
        checkData.put(data.sid, data.sname);
    } else {
        checkData.remove(data.sid);
    }
    var kset = checkData.keySet();
    var html = "";
    for (var i in kset) {
        var value = checkData.get(kset[i]);
        html += "<span id='" + kset[i] + "'><input id='" + kset[i] + "' name='"
            + kset[i] + "' type='checkbox' value='" + value
            + "'  onclick='checkItem(event)' class='selectedItem'>" + value + "</input></span>";
    }
    $("#Chtext").html(html);
}

function gridCheckedAll(checked) {
    if (checked) {
        var checkStatus = layui.table.checkStatus('psmlist');
        var data = checkStatus.data;
        for (var i in data) {
            checkData.put(data[i].sid, data[i].sname);
        }
    } else {
        checkData = new Map();
    }
    var kset = checkData.keySet();
    var html = "";
    for (var i in kset) {
        var value = checkData.get(kset[i]);
        html += "<span id='" + kset[i] + "'><input id='" + kset[i] + "' name='"
            + kset[i] + "' type='checkbox' value='" + value
            + "'  onclick='checkItem(event)' class='selectedItem'>" + value + "</input></span>";
    }
    $("#Chtext").html(html);
}

// 删除
var chid = '';

function deleteBills() {
    $("span[id='" + chid + "']").remove();
    checkData.remove(chid);
}

function checkItem(event) {
    $("input").bind("click", function () {
        chid = $(this).attr("id");
    });
}

function deleteAll() {
    $("#Chtext").html("");
    checkData = new Map();
    loadList();
}

// 确定-返回
function dailogEngin() {
    var tid = [];
    var txt = [];
    $(".selectedItem").each(function () {
        tid.push($(this).attr("name"));
        txt.push($(this).attr("value"));
    });
    var prams = {
        "id": tid.join(","),
        "name": txt.join(",")
    };
    return prams;
}