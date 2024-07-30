// loaded by the plots.html template

/* Scott D. Anderson
   July 2024 first version copied from 2022 code in plots.html

   TO DO:
   - should rewrite this in camelCase instead of snake_case

   ASSUMPTIONS:
   - There is a global duration_hours that is the desired plot duration in hours (integer)

*/

// dates. These functions should probably have their own file

function to_date(datetime_str, opt_timestr) {
    const dt_str = opt_timestr ? datetime_str + " " + opt_timestr : datetime_str;
    try {
        return new Date(dt_str);
    } catch (err) {
        console.error('Not a proper datetime str: ', datetime_str, opt_timestr);
        throw err;
    }
}

function date_to_ISO_datestring(date) {
    // dunno why this method doesn't exist
    const yyyy = date.getFullYear();
    const m = date.getMonth()+1;
    const mm = m<10?"0"+m:""+m;
    const d = date.getDate();
    const dd = d<10?"0"+d:""+d;
    return yyyy+'-'+mm+'-'+dd;
}

function date_to_ISO_timestring(date) {
    // dunno why this method doesn't exist
    const h = date.getHours();
    const m = date.getMinutes();
    return (h<10 ? "0"+h : ""+h)
        +":"
        +(m<10 ? "0"+m : ""+m);
}

// obsolete
function to_start_datetime_str(start) {
    // argument is probably a string, but can also be a datetime object
    try {
        start = to_date(start);
        // sets the globals
        start_datetime = start;
        start_datetime_str = date_to_ISO_datestring(start)+" "+date_to_ISO_timestring(start);
        return start_datetime_str;
    } catch (err) {
        console.error('start is not a proper datetime: ',start);
        throw err;
    }
}


// sets a global, duration_hours, 

function to_duration(duration) {
    try {
        if( (typeof duration === typeof 2) &&
            duration > 0 &&
            duration < 24 ) {
            // 
            duration = Math.round(duration);
            // set global
            duration_hours = duration;
            return duration;
        }
    } catch (err) {
        console.error('duration is not a small, positive integer: ',duration);
        throw err;
    }
}

// Returns minutes since midnight on that date

function datetime_to_minutes(datetime) {
    let date = new Date(datetime);
    return date.getHours()*60 + date.getMinutes();
}

// returns an array of integers from startmin to endmin by 5. 
// currently used for labelling plotted points

function timesteps(startmin, endmin) {
    let vals = [];
    for(let mins = startmin; mins <= endmin; mins += 5) {
        vals.push(mins);
    }
    return vals;
}

// returns a timestring for the given number of minutes since midnight. E.g. 80 => 01:20
// currently used for labelling plotted points

function minutes_to_timestr(mins) {
    let hh = Math.floor(mins/60);
    let mm = mins - hh*60;
    hh = hh % 24;
    
    return (hh<10?"0"+hh:""+hh)
        +":"
        +(mm<10?"0"+mm:""+mm);
}




// Return a URL for getting the data. References a global variable data_url_base

function data_url(date, time, duration) {
    // to do: add debugging
    let start = new Date(date + " " + time);
    let start_date = date_to_ISO_datestring(start);
    let start_time = date_to_ISO_timestring(start);
    // finally, we get to work
    const slash = "/";
    return data_url_base + start_date + slash + start_time + slash + duration;
}

// Return a URL for the current page to display data for the given
// date, start time, and duration. Used to redirect to the proper URL.

function page_url(date, time, duration) {
    // to do: add debugging
    let start = new Date(date + " " + time);
    let start_date = date_to_ISO_datestring(start);
    let start_time = date_to_ISO_timestring(start);
    // finally, we get to work
    const slash = "/";
    return page_url_base + start_date + slash + start_time + slash + duration;
}

// Plotting functions

/* Plot the insulin (boluses, prog_basal (programmed basal rates) and
 * actual_basal versus time. Time is given by times_str, which is an
 * array of strings like "01:20" for 1:20am. The plot is put on the
 * element whose id is displayElementId. Also plots the CGM on the
 * second Y axis (on the right). */

function update_insulin_plot(displayElementId, times_str, data) {
    const cgmColor = 'rgb(203, 66, 245)';
    const diColor = 'green';
    const insulinColor = 'rgb(31, 119, 180)';
    // y axis on the right
    const trace_cgm = {x: times_str,
                       y: data.cgm,
                       yaxis: 'y', // necessary to put this on the right-hand axis
                       line: {
                           color: cgmColor,
                           width: 2},
                       type: "line",
                       name: "CGM"};
    // 3 insulin traces on y2
    const trace_boluses = { x: times_str,
                            y: data.boluses,
                            yaxis: 'y2',
                            type: "bar",
                            marker: {color: insulinColor},
                            name: "bolus"};
    const trace_used_basal = {x: times_str,
                              y: data.actual_basal,
                              yaxis: 'y2',
                              type: "line",
                              line: {color: insulinColor,
                                     width: 1},
                              name: "actual basal"};
    const trace_extended_bolus = {x: times_str,
                                  y: data.extended,
                                  yaxis: 'y2',
                                  type: "line",
                                  line: {color: insulinColor,
                                         width: 1},
                                  name: "extended bolus"};
    // DI trace on y3
    const trace_dynamic_insulin = {x: times_str,
                                   y: data.dynamic_insulin,
                                   yaxis: 'y3',
                                   type: "line",
                                   line: {color: diColor, width: 2},
                                   name: "dynamic insulin"};
    const traces = [trace_boluses,
                    // trace_prog_basal,
                    trace_used_basal,
                    // trace_extended_bolus,
                    trace_dynamic_insulin,
                    trace_cgm
                   ];
    // Display using Plotly
    var layout = {title: "Insulin plot",
                  // this says that the x-axis takes up this part of
                  // the horizontal space for the graphic, leaving a little
                  // space for the left y-axes, which are at 0 and 0.1
                  xaxis: {domain: [0.1, 1]},
                  showlegend: true,
                  yaxis: {title: "CGM",
                           titlefont: {color: cgmColor},
                           tickfont: {color: cgmColor},
                           side: 'right'
                         },
                  yaxis2: {title: "insulin",
                           titlefont: {color: insulinColor},
                           tickfont: {color: insulinColor},
                           overlaying: 'y',
                           side: 'left',
                           anchor: 'free',
                           position: 0
                          },
                  yaxis3: {title: "dynamic insulin",
                           titlefont: {color: diColor},
                           tickfont: {color: diColor},
                           overlaying: 'y',
                           side: 'left',
                           // the following two properties position this y axis offset from yaxis2
                           anchor: 'free',
                           position: 0.1
                          }
                           
                  /*
                  ,legend: {
                      x: 1,
                      xanchor: 'right',
                      y: 0}
                  */
                 };
    var config = {responsive: true};
    Plotly.newPlot(displayElementId, traces, layout, config);
}

function update_carbs_plot(displayElementId, times_str, data) {
    const cgmColor = 'rgb(203, 66, 245)';
    const dcColor = 'orange';
    const carbColor = 'purple';
    // y axis on the right
    const trace_cgm = {x: times_str,
                       y: data.cgm,
                       yaxis: 'y', // necessary to put this on the right-hand axis
                       line: {
                           color: cgmColor,
                           width: 2},
                       type: "line",
                       name: "CGM"};
    // 2 carb traces on y2
    const trace_carbs = { x: times_str,
                          y: data.carbs,
                            yaxis: 'y2',
                            type: "bar",
                            marker: {color: carbColor},
                            name: "carbs"};
    // DC trace on y3
    const trace_dynamic_carbs = {x: times_str,
                                 y: data.dynamic_carbs,
                                 yaxis: 'y3',
                                 type: "line",
                                 line: {color: dcColor, width: 2},
                                 name: "dynamic carbs"};
    const traces = [trace_carbs,
                    trace_dynamic_carbs,
                    trace_cgm
                   ];
    // Display using Plotly
    var layout = {title: "Carb plot",
                  // this says that the x-axis takes up this part of
                  // the horizontal space for the graphic, leaving a little
                  // space for the left y-axes, which are at 0 and 0.1
                  xaxis: {domain: [0.1, 1]},
                  showlegend: true,
                  yaxis: {title: "CGM",
                           titlefont: {color: cgmColor},
                           tickfont: {color: cgmColor},
                           side: 'right'
                         },
                  yaxis2: {title: "carbs",
                           titlefont: {color: carbColor},
                           tickfont: {color: carbColor},
                           overlaying: 'y',
                           side: 'left',
                           anchor: 'free',
                           position: 0
                          },
                  yaxis3: {title: "dynamic carbs",
                           titlefont: {color: dcColor},
                           tickfont: {color: dcColor},
                           overlaying: 'y',
                           side: 'left',
                           // the following two properties position this y axis offset from yaxis2
                           anchor: 'free',
                           position: 0.1
                          }
                 };
    var config = {responsive: true};
    Plotly.newPlot(displayElementId, traces, layout, config);
}
    

function update_cgm_plot(displayElementId, times_str, cgm_values) {
    var trace_cgm_values = {x: times_str,
                            y: cgm_values,
                            type: "line",
                            name: "realtime CGM"};
    var config = {responsive: true,
                  yaxis: {range: [0, 300]}};
    Plotly.newPlot(displayElementId,
                   [trace_cgm_values],
                   {title: "realtime CGM plot",
                    showlegend: false},
                   config);
}
