from scipy import signal, integrate
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import datetime
import sys
import cv2
import math




def visualise(csv,min,max):
    data = pd.read_csv(csv)
    try:
        data = data.drop("Unnamed: 97",axis=1)
    except Exception:
        pass
    data =data.melt(id_vars=["Timestamp"],var_name="location",value_name="Temperature")
    letters_to_numbers = {
            "A":0,
            "B": 1,
            "C": 2,
            "D": 3,
            "E": 4,
            "F": 5,
            "G": 6,
            "H": 7,
        }
    x_list = []
    y_list = []
    size_list = []
    for i, row in data.iterrows():
        location = row["location"]
        y = int(location[:-1])
        x = location[-1]
        x_list.append(x)
        y_list.append(y)
        size_list.append(10)
    data["x"] = x_list
    data["y"] = y_list
    data["size"] = size_list
    data = data.drop("location",axis=1)
    fig = px.scatter(data,x="y",y="x",color="Temperature",animation_frame="Timestamp",size="Temperature",range_color=(min,max))
    fig.show()
        
if __name__ == "__main__":
    visualise("test_13_T.csv",min=22,max=25)