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
$("#calculations").toggle();

var isf_value = 50;		// just a default. Should make this configurable.

function calculate_ideal_ic(isf) {
    /* The deviations from idea range (80-120) for one or two
     three-hour periods post-meal have already been calculated in the
     back end and have been saved in variables named bg_excess_period1
     and bg_exess_period2.
    */
    console.log("calc ideal ic using ",isf,bg_excess_period1,bg_excess_period2);
}


$("#isf_value").text(isf_value);

$("#isf_slider").slider({
    min: 0,
    max: 100,
    value: isf_value,
    slide: function(event, ui) {
	isf_value = ui.value;	// not sure we need this
	$("#isf_value").text(ui.value);
	calculate_ideal_ic(ui.value);
    }
});


