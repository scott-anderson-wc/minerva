-- create data suitable for an Excel file but with hyperlinks to the raw data

select rtime,isf,bg0,bg1,bolus,
       concat('http://minervadiabetes.net/scott/prod/md/browseisf/',
		date(rtime),'%20',time(rtime)) as 'detail url'
 	from isfvals;
	
