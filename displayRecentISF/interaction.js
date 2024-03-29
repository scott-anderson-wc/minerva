// JavaScript File

/* global $ */
var URL = '/getRecentISF/';
var example_ajax_response = {
    Q1: 4,
    Q2: 24,
    Q3: 48,
    time_bucket: 0,
    weeks_of_data: 4,
    number_of_data: 55,
    min_number_of_data: 50,
    timestamp_of_calculation: null
};
var ajax_response = example_ajax_response;

function updatePage(data) {
    for (let p in data) {
        // the element ids have to match the keys above! 
        let elt = document.getElementById(p);
        elt.textContent = data[p];
    }
    $("#input_min_number_of_data").val(ajax_response.min_number_of_data);
}
var load_time_of_data = null;

function loadData() {
    if (false) {
        let bucket = ajax_response.time_bucket;
        let weeks = ajax_response.weeks_of_data;
        let min_data = ajax_response.min_number_of_data;
        let URL_plus = `${URL}/${bucket}/${weeks}/${min_data}`;
        console.log(URL_plus);
        // $.get(URL_plus, function (data) { ajax_response = data; updatePage(data); });
    }
    else {
        load_time_of_data = new Date();
        ajax_response.timestamp_of_calculation = niceDateTimeStr(load_time_of_data);
        // don't need this, because the back-end can't change the time_bucket, right?
        // ajax_response.bucket_description = bucketTime(ajax_response.time_bucket);
        updatePage(ajax_response);
        placeQuartiles();
    }
}

function dateStr(d) {
    let dd = d.getDate().toString().padStart(2, '0');
    let mm = d.getMonth().toString().padStart(2, '0');
    let yyyy = d.getFullYear();
    return `${yyyy}-${mm}-${dd}`;
}

function fullStr(d) {
    return d.toDateString() + ' ' + d.toTimeString();
}

function niceDateTimeStr(d) {
    let now = new Date();
    let yesterday = new Date();
    // this really works. If you set the date to zero, it's the
    // last day of the previous month.
    yesterday.setDate(yesterday.getDate() - 1);
    if (dateStr(now) === dateStr(d)) {
        return "Today at " + d.toTimeString();
    }
    else if (dateStr(yesterday) === dateStr(d)) {
        return "Yesterday at " + d.toTimeString();
    }
    else {
        return fullStr(d);
    }
}

function bucketTime(n) {
    var strs = ["midnight to 2am",
        "2am to 4am",
        "4am to 6am",
        "6am to 8am",
        "8am to 10am",
        "10am to noon",
        "noon to 2pm",
        "2pm to 4pm",
        "4pm to 6pm",
        "6pm to 8pm",
        "8pm to 10pm",
        "10pm to midnight"
    ];
    return strs[n / 2];
}

function placeElt(parent, child, where) {
    let p = $(parent);
    let c = $(child);
    let ph = p.height(),
        pw = p.width();
    let ch = c.height(),
        cw = c.width();
    let left = null,
        top = null;
    if (where.left == 'left')
        left = cw * 0.5;
    else if (where.left == 'right')
        left = pw - cw * 0.5;
    else if (where.left == 'middle')
        left = (pw - cw) * 0.5;
    if (where.top == 'top')
        top = 0 - ch * 0.5;
    else if (where.top == 'bottom')
        top = ph - ch * 0.5;
    else if (where.top == 'middle')
        top = (ph - ch) * 0.5;
    $(c).css({ top: top, left: left });
}

function placeQuartiles() {
    placeElt('#box', '#Q3', { top: 'top', left: 'middle' });
    placeElt('#box', '#Q1', { top: 'bottom', left: 'middle' });
    placeElt('#box', '#Q2', { top: 'middle', left: 'middle' });
}
$(window).on('resize', placeQuartiles);

loadData();
$('#refresh').on('click', loadData);
$("#input_min_number_of_data").hide();
$("#input_min_number_of_data").on('change', function(event) {
    event.preventDefault();
    var str = $("#input_min_number_of_data").val();
    try {
        var num = parseInt(str, 10);
    }
    catch (err) {
        console.log(`Not a Number: ${str} error is ` + err);
        // restore old value
        $("#input_min_number_of_data").val(ajax_response.min_number_of_data);
    }
    ajax_response.min_number_of_data = num;
    $("#min_number_of_data").text(num);
    $("#input_min_number_of_data").blur().hide();
});
$("#min_number_of_data").on('click', function(event) {
    $("#input_min_number_of_data").show().focus();
});

$("#input_weeks_of_data").hide().on('change', function(event) {
    event.preventDefault();
    var str = $("#input_weeks_of_data").val();
    try {
        var num = parseInt(str, 10);
    }
    catch (err) {
        console.log(`Not a Number: ${str} error is ` + err);
        // restore old value
        $("#input_weeks_of_data").val(ajax_response.weeks_of_data);
    }
    ajax_response.weeks_of_data = num;
    $("#weeks_of_data").text(num);
    $("#input_weeks_of_data").blur().hide();
});
$("#weeks_of_data").on('click', function(event) {
    $("#input_weeks_of_data").show().focus();
});

function setupTimeBucketMenu() {
    var $select = $("<select>").attr('id', 'select_time_bucket');
    for (let i = 0; i < 12; i++) {
        let b = i * 2;
        let desc = bucketTime(b);
        let $opt = $("<option>").attr('value',b);
        if (b === ajax_response.time_bucket) {
            $opt.attr('selected', true);
        }
        $opt.text(desc).appendTo($select);
    }
    $select.on('change', function(event) {
        event.preventDefault();
        var str = $("#select_time_bucket").val(); // maybe $(this)?
        try {
            var num = parseInt(str, 10);
        }
        catch (err) {
            console.log(`Not a Number: ${str} error is ` + err);
            // restore old value
            $("#select_time_bucket").val(ajax_response.time_bucket);
        }
        ajax_response.time_bucket = num;
        $("#time_bucket").text(num);
    });
    $("#bucket_description").html($select);
}
setupTimeBucketMenu();
