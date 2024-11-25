from scipy import signal, integrate
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import datetime


def calculate_porus(csv, normalize="12H"):
    data = pd.read_csv(csv)
    fig = go.Figure()
    n_peaks_dict = {}
    magnitude_dict = {}
    integral_dict = {}
    first_time = datetime.datetime.strptime(data["Timestamp"][0], "%H:%M:%S.%f")
    data["Timestamp"] = data["Timestamp"].apply(
        lambda x: (datetime.datetime.strptime(x, "%H:%M:%S.%f")-first_time).total_seconds())
    for column in data.columns:
        if column == "Timestamp":
            continue
        normalized = data[column] - data[normalize]
        fig.add_trace(
            go.Scatter(
                x=data["Timestamp"],
                y=normalized,
                mode="lines",
                name=column,
            )
        )
        peaks = signal.find_peaks(normalized, height=0.15, distance=200)[0]
        
        if len(peaks) == 0:
            print(f"No peaks found for {column}")
            continue
        integrals = []
        for peak in peaks:
            integrals.append(integrate.trapezoid(normalized[peak-30:peak+300],data["Timestamp"][peak-30:peak + 300]))
            fig.add_annotation(text=f"{integrals[-1]:.2f}",x=data["Timestamp"][peak]+20,y=normalized[peak], showarrow=False)
        n_peaks_dict[column] = len(peaks)
        integral_dict[column] = integrals
        magnitude_dict[column] = sum([normalized[i] for i in peaks])
        fig.add_trace(
            go.Scatter(
                x=[data["Timestamp"][peak] for peak in peaks],
                y=[normalized[i] for i in peaks],
                mode="markers",
                marker=dict(size=8, color="red", symbol="cross"),
                name=f"{column} peaks",
            )
        )
        
    fig.show()
    print(n_peaks_dict)
    print(magnitude_dict)
    print(integral_dict)
    


if __name__ == "__main__":
    calculate_porus("RC_Test4T.csv")
