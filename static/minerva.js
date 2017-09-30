console.log("Minerva JS loaded");

/* maybe these should be dynamic, but eventually, 
 * the maxDate will be today (live data) and 
 * the minDate will never change. */

$("#date_human").datepicker({ 
    // US date format
    minDate: new Date("5/19/2014"), 
    maxDate: new Date("2/20/2017"),
    changeMonth: true,
    dateFormat: "yy-mm-dd",
    altField: "#date_submitted",
    altFormat: "yy-mm-dd"
});

/*
$("#cgm_date").datepicker({ minDate: new Date(2016,8,12), 
                            maxDate: new Date(2017,1,23),
                            changeMonth: true,
                            changeYear: true });

*/

$("#toggle_calculations").click(function () {
    console.log("Toggle Calculations");
    $("#calculations").toggle();
});
