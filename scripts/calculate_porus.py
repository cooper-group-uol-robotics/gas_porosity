from scipy import signal, integrate
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import datetime
import sys


def calculate_porus(csv,threshold):
    data = pd.read_csv(csv)
    fig = go.Figure()
    n_peaks_dict = {}
    magnitude_dict = {}
    integral_dict = {}
    first_time = datetime.datetime.strptime(data["Timestamp"][0], "%H:%M:%S.%f")
    data= data.drop("Unnamed: 97",axis=1)
    data["Timestamp"] = data["Timestamp"].apply(
        lambda x: (datetime.datetime.strptime(x, "%H:%M:%S.%f")-first_time).total_seconds())
    for column in data.columns:
        if column == "Timestamp":
            continue
            
        normalized = data[column] - data[column][0]
        normalized = normalized + abs(min(normalized))
        filtered = signal.medfilt(normalized,kernel_size=5)
        fig.add_trace(
            go.Scatter(
                x=data["Timestamp"],
                y=filtered,
                mode="lines",
                name=column,
            )
        )
        peaks = signal.find_peaks(filtered, height=threshold, distance=200)[0]
        
        if len(peaks) == 0:
            print(f"No peaks found for {column}")
            integrals = []
        else:
           
            for peak in peaks:
                integrals.append(integrate.trapezoid(filtered[peak-30:peak+300],data["Timestamp"][peak-30:peak + 300]))
                #minus the square
                fig.add_annotation(text=f"{integrals[-1]:.2f}",x=data["Timestamp"][peak],y=filtered[peak], showarrow=True)
        
        n_peaks_dict[column] = len(peaks)
        integral_dict[column] = integrals
        magnitude_dict[column] = sum([filtered[i] for i in peaks])
        fig.add_trace(
            go.Scatter(
                x=[data["Timestamp"][peak] for peak in peaks],
                y=[filtered[i] for i in peaks],
                mode="markers",
                marker=dict(size=8, color="red", symbol="cross"),
                name=f"{column} peaks",
            )
        )
        
    fig.show()
    print(n_peaks_dict)
    print(integral_dict)
    
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
    
    cols = 12
    rows = 8
    grid = np.zeros((9,13))
    peaks_df = pd.DataFrame.from_dict(n_peaks_dict,orient="index")
    print(peaks_df)
    for key in n_peaks_dict.keys():
        letter = key[-1]
        num = int(key[:-1])
        grid[letters_to_numbers[letter]][num] = n_peaks_dict[key]
    
    fig2 = go.Figure(data=go.Heatmap(
    z=grid,
    colorscale='viridis'
    ))
    
    # --- Add gridlines ---
    shapes = []

    # Vertical grid lines
    for c in range(cols + 1):
        shapes.append(dict(
            type="line",
            x0=c - 0.5, x1=c - 0.5,
            y0=-0.5, y1=rows+1 - 0.5,
            line=dict(color="white", width=1)
        ))

    # Horizontal grid lines
    for r in range(rows + 1):
        shapes.append(dict(
            type="line",
            x0=-0.5, x1=cols+1 - 0.5,
            y0=r - 0.5, y1=r - 0.5,
            line=dict(color="white", width=1)
        ))
    
    fig2.update_layout(shapes=shapes)
    
    fig2.show()
    
    

   


if __name__ == "__main__":
    calculate_porus("test_13_T.csv",threshold=0.7)
    #calculate_porus(str(sys.argv[1]),str(sys.argv[2]))