import pandas as pd
import numpy as np
from datetime import datetime,date, timedelta

! pip install geopandas
import geopandas as gpd
from geopandas import GeoDataFrame as gdf

from google.colab import files

import folium
from folium import Choropleth, Circle, Marker
from folium.plugins import HeatMap, MarkerCluster

from google.colab import drive
drive.mount('/content/drive')

path_raw_data = '/content/drive/Shareddrives/MSc - Shiveswarran/Raw Data/digana_2022_08.csv'
path_trip_ends = '/content/drive/Shareddrives/MSc - Shiveswarran/Processed data/Kandy-Digana Aug 2022/trip_ends.csv'
path_bus_trips = '/content/drive/Shareddrives/MSc - Shiveswarran/Processed data/Kandy-Digana Aug 2022/bus_trips.csv'
path_bus_stops = '/content/drive/Shareddrives/MSc - Shiveswarran/Raw Data/bus_stops_654.csv'

raw_data = pd.read_csv(path_raw_data)
trip_ends = pd.read_csv(path_trip_ends)
bus_trips = pd.read_csv(path_bus_trips)
bus_stops= pd.read_csv(path_bus_stops)

def raw_data_cleaning(raw_data):
  #raw_data = raw_data.drop(drop_columns, axis = 1)
  
  gps_data = raw_data[raw_data.latitude != 0]
  gps_data = gps_data[gps_data.longitude != 0] #cleaning zero values for latitude & longitude

  gps_data['date'] = pd.to_datetime(gps_data['devicetime']).dt.date #split date and time separately into datetime variables
  gps_data['time'] = pd.to_datetime(gps_data['devicetime']).dt.time

  gps_data = gps_data.sort_values(['deviceid', 'date', 'time']) #sorting dataset by time and device

  return gps_data

raw_data.columns

additional_columns = ['servertime','fixtime','address','routeid']

#drop_columns = ['servertime','fixtime','address','routeid']
gps_data= raw_data_cleaning(raw_data)

def bus_stop_buffer_create(gps_data,bus_stops,stop_buffer,extra_buffer):

  #Create Geodataframe of GPS data and bus stops data
  gps_data = gpd.GeoDataFrame(gps_data, geometry=gpd.points_from_xy(gps_data.longitude,gps_data.latitude),crs='EPSG:4326')
  bus_stops = gpd.GeoDataFrame(bus_stops, geometry=gpd.points_from_xy(bus_stops.longitude,bus_stops.latitude),crs='EPSG:4326')

  #project the corrdinates in Local coordinate system
  bus_stops = bus_stops.to_crs('EPSG:5234')
  gps_data = gps_data.to_crs('EPSG:5234')

  #split bus stops dataframe into two based on route direction 
  bus_stops_direction1 = bus_stops[bus_stops['direction']=='Kandy-Digana']
  bus_stops_direction2 = bus_stops[bus_stops['direction']=='Digana-Kandy']

  bus_stops_direction2.reset_index(drop = True, inplace = True)

  #proximity analysis
  #creating a buffer
  bus_stops_buffer1 = gpd.GeoDataFrame(bus_stops_direction1, geometry = bus_stops_direction1.geometry.buffer(stop_buffer))
  bus_stops_buffer2 = gpd.GeoDataFrame(bus_stops_direction2, geometry = bus_stops_direction2.geometry.buffer(stop_buffer))

  #creating additional extra buffer to accomodate points if they were missed in standard stop buffer
  bus_stops_buffer1_add = gpd.GeoDataFrame(bus_stops_direction1, geometry = bus_stops_direction1.geometry.buffer(extra_buffer))
  bus_stops_buffer2_add = gpd.GeoDataFrame(bus_stops_direction2, geometry = bus_stops_direction2.geometry.buffer(extra_buffer))

  return bus_stops_buffer1, bus_stops_buffer2,gps_data,bus_stops_buffer1_add,bus_stops_buffer2_add

stop_buffer = 50
extra_buffer = 100
bus_stops_buffer1, bus_stops_buffer2,gps_data,bus_stops_buffer1_add,bus_stops_buffer2_add = bus_stop_buffer_create(gps_data,bus_stops,stop_buffer,extra_buffer)

def bus_trajectory(gps_data,trip_ends,bus_trips):
  #gps records that are matched with end terminals, are merged with whole GPS records
  trip_ends = trip_ends[['id','bus_stop','trip_id']]
  bus_trajectory = pd.merge(left = gps_data, right  = trip_ends,how = 'outer',left_on ='id', right_on= 'id')

  #gps records that are not associated with the terminals are asssigned as trip id = 0
  bus_trajectory["trip_id"].fillna(0, inplace = True)

  #run a loop to assign trip_id to records that are in between the terminals
  bus_trajectory.reset_index(drop = True, inplace = True)

  trip =1
  for i in range(len(bus_trajectory)-1):
    if (bus_trajectory.at[i,'trip_id']==trip) & (bus_trajectory.at[i+1, 'trip_id'] == 0):
      bus_trajectory.at[i+1,'trip_id'] = trip
    elif (bus_trajectory.at[i,'trip_id']==trip) & (bus_trajectory.at[i+1, 'trip_id'] == trip):
      trip = trip + 1
  
  bus_trajectory.drop(bus_trajectory[bus_trajectory['trip_id']==0].index, inplace = True ) #drop records that are not identified as a bus trip

  #Identify the directions of each bus trajectories using bus trips extracted data
  directions= bus_trips.set_index('trip_id').to_dict()['direction']
  bus_trajectory['direction'] = list(map(lambda x: directions[x]   ,bus_trajectory['trip_id']))

  return bus_trajectory

bus_trajectory = bus_trajectory(gps_data,trip_ends,bus_trips)

def download_csv(data,filename):
  filename= filename + '.csv'
  data.to_csv(filename, encoding = 'utf-8-sig',index= False)
  files.download(filename)

def stop_buffer_filter(bus_trajectory,bus_stops_buffer1,bus_stops_buffer2,bus_stops_buffer1_add,bus_stops_buffer2_add):

  #project to local coordinate system before buffer filtering
  bus_trajectory = bus_trajectory.to_crs('EPSG:5234')

  #split trajectories by direction 
  trajectory_dir_1 = bus_trajectory[bus_trajectory['direction'] == 1]
  trajectory_dir_2 = bus_trajectory[bus_trajectory['direction'] == 2]

  #reset index before for loop
  trajectory_dir_1.reset_index(drop = True, inplace = True)
  trajectory_dir_2.reset_index(drop = True, inplace = True)

  #filter records within bus stops buffer of both directions
  for i in range(len(trajectory_dir_1)):
    for stop in range(len(bus_stops_buffer1)):
      if bus_stops_buffer1.iloc[stop].geometry.contains(trajectory_dir_1.iloc[i].geometry):
        trajectory_dir_1.at[i,'bus_stop'] = bus_stops_buffer1.at[stop,'stop_id']
      else:       
        if bus_stops_buffer1_add.iloc[stop].geometry.contains(trajectory_dir_1.iloc[i].geometry):
          trajectory_dir_1.at[i,'bus_stop'] = bus_stops_buffer1_add.at[stop,'stop_id']

  for i in range(len(trajectory_dir_2)):
    for stop in range(len(bus_stops_buffer2)):
      if bus_stops_buffer2.iloc[stop].geometry.contains(trajectory_dir_2.iloc[i].geometry):
        trajectory_dir_2.at[i,'bus_stop'] = bus_stops_buffer2.at[stop,'stop_id']
      else:        
        if bus_stops_buffer2_add.iloc[stop].geometry.contains(trajectory_dir_2.iloc[i].geometry):
          trajectory_dir_2.at[i,'bus_stop'] = bus_stops_buffer2_add.at[stop,'stop_id']        

  #concatenate dataframes of both directions and keep only records filtered within bus stops
  bus_trip_all_points = pd.concat([trajectory_dir_1,trajectory_dir_2])
  bus_stop_all_points = bus_trip_all_points.dropna()

  return bus_trip_all_points,bus_stop_all_points

bus_trajectory

download_csv(bus_trip_all_points,'bus_trip_all_points')

#bus_trip_all_points = pd.read_csv('/content/drive/Shareddrives/MSc - Shiveswarran/Processed data/Bus_trip_all_points/bus_trip_all_points_2021_09.csv')
#bus_stop_all_points = bus_trip_all_points.dropna()
#bus_stop_all_points

#bus_stop_all_points['date'] = pd.to_datetime(bus_stop_all_points['date']).dt.date 
#bus_stop_all_points['time'] = pd.to_datetime(bus_stop_all_points['time']).dt.time

def dwell_time_estimation(bus_stop_all_points):
  
  #Drop records with End Bus terminals 
  bus_stop_all_points.drop(bus_stop_all_points[bus_stop_all_points['bus_stop'] == 'BT01'].index, inplace = True)
  bus_stop_all_points.drop(bus_stop_all_points[bus_stop_all_points['bus_stop'] == 'BT02'].index, inplace = True)

  #grouping all records filtered for every bus stop
  bus_stop_all_points['grouped_ends'] = ((bus_stop_all_points['bus_stop'].shift() != bus_stop_all_points['bus_stop'])).cumsum()

  #creating a new dataframe for bus stop times
  columns = ['trip_id','deviceid','date','direction','bus_stop', 'arrival_time','departure_time','dwell_time']
  bus_stop_times = pd.DataFrame(columns=columns)

  #Loop over every grouped filtered records and choose the two records that indicate bus arrival and departure to the stop 
  for name, group in bus_stop_all_points.groupby('grouped_ends'):
    if 0 in group['speed'].values:               #if the grouped filter record has '0" speed values, then bus has stopped more than 15 seconds there and first '0'speed record as the arrival
      values = []
      trip_id = np.unique(group['trip_id'].values)[0]
      direction = np.unique(group['direction'].values)[0]
      deviceid = np.unique(group['deviceid'].values)[0]
      date = np.unique(group['date'].values)[0]
      bus_stop = np.unique(group['bus_stop'].values)[0]

      arrival_time = group[group['speed']==0]['time'].min()
      
      buffer_leaving_time = group['time'].max()
      rough_departure_time = group[group['speed']==0]['time'].max() 

      if (datetime.combine(date.min,buffer_leaving_time) - datetime.combine(date.min,rough_departure_time)).total_seconds() > 15:
        departure_time = (datetime.combine(date.min,rough_departure_time) + timedelta(seconds =15)).time()
      else:
        departure_time = buffer_leaving_time

      values.extend([trip_id,deviceid,date,direction,bus_stop,arrival_time,departure_time])
      bus_stop_times = bus_stop_times.append(dict(zip(columns,values)),True)

    else:
      values = []
      trip_id = np.unique(group[['trip_id']].values)[0]
      direction = np.unique(group['direction'].values)[0]
      deviceid = np.unique(group[['deviceid']].values)[0]
      date = np.unique(group['date'].values)[0]
      bus_stop = np.unique(group['bus_stop'].values)[0]  

      arrival_time = group['time'].min()
      departure_time = arrival_time

      values.extend([trip_id,deviceid,date,direction,bus_stop,arrival_time,departure_time])
      bus_stop_times = bus_stop_times.append(dict(zip(columns,values)),True)

  for i in range(len(bus_stop_times)):
    bus_stop_times.at[i,'dwell_time'] = datetime.combine(date.min,bus_stop_times.at[i,'departure_time']) - datetime.combine(date.min,bus_stop_times.at[i,'arrival_time'])

  bus_stop_times['dwell_time_in_seconds'] =  bus_stop_times['dwell_time']/np.timedelta64(1,'s')

  return bus_stop_times

bus_stop_times = dwell_time_estimation(bus_stop_all_points)

def dwell_time_feature_addition(bus_stop_times):

  #bus_stop_times = bus_stop_times.drop(bus_stop_times[bus_stop_times['dwell_time_in_seconds']>threshold].index )

  bus_stop_times['day_of_week'] = pd.to_datetime(bus_stop_times['date']).dt.weekday
  bus_stop_times['hour_of_day'] = list(map(lambda x: x.hour, (bus_stop_times['arrival_time'])))
  bus_stop_times['weekday/end'] = list(map(lambda x: 1 if x < 5 else 0 , (bus_stop_times['day_of_week'])))

  return bus_stop_times

threshold = 480
bus_stop_times = dwell_time_feature_addition(bus_stop_times)
download_csv(bus_stop_times,'bus_stop_times')

bus_stop_times.head(1000)

def trip_visualization(trip_id, city_location,bus_stop_dir_1):
  trip = bus_trajectory[bus_trajectory['trip_id']==trip_id]
  trip = trip.to_crs('EPSG:4326')
  bus_stops_dir_1 = bus_stops_dir_1.to_crs('EPSG:4326')

  map = folium.Map(location=city_location, tiles='openstreetmap', zoom_start=14)
  for idx, row in trip.iterrows():
    Marker([row['latitude'], row['longitude']]).add_to(map)

  bus_stops_map = folium.Map(location=city_location, tiles='openstreetmap', zoom_start=14)
  for idx, row in bus_stop_dir_1.iterrows():
    Marker([row['latitude'], row['longitude']]).add_to(bus_stops_map)
  
  return map, bus_stops_map
