import PySimpleGUI as sg
import pandas as pd
from os import walk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

def process_raw_directory(path, animal_list_path, day_start="06:00", day_end="18:00"):
    # This function walks through a given directory to load the Excel files
    # into a pandas DataFrame for further processing
    #
    # Parameters:
    #
    # path - string; Defines the directory to walk through
    # animal_list_path - string; Gives the path+filename for the animal list

    # Load animal list
    animal_list = pd.read_excel(animal_list_path, header=0)

    # Iterate through the files in the directory containing the recordings
    f = []
    for (dir_path, dir_names, file_names) in walk(path):
        f.extend(file_names)
        break

    complete_data = pd.DataFrame() # This DataFrame will contain all data in the end
    for filename in f:
        if filename in animal_list["Filename"].values:
            group = animal_list[animal_list["Filename"]==filename]["Group"].values[0]
            animal = animal_list[animal_list["Filename"]==filename]["Animal_ID"].values[0]
            data = pd.read_excel(f"{path}/{filename}", header=1)
            data.columns = ["time", "systolic", "map", "hr", "diastolic", "activity"]
            data = data.set_index("time").resample("5T").mean()  # Resample to 5 minute intervals
            data["rel_time"] = data.index - pd.Timestamp(
                data.index[0].date())  # Add a time stamp relative to the start of the experiment
            data["rel_time"] = data["rel_time"].astype("timedelta64[m]")/(24*60)
            data["time_of_day"] = data.index.time  # Add the time of day as a separate column

            # The column "night" is either 1 for times between day_end and day_start or 0 during the day
            data["night"] = 1  # Set everything to 1
            # Set values between day_start and day_end to 0
            data.iloc[
                data.index.indexer_between_time(day_start, day_end, include_start=True, include_end=True),
                data.columns.get_loc('night')] = 0

            data["group"] = group
            data["animal"] = animal
            data["amplitude"] = data.systolic - data.diastolic

            complete_data = pd.concat([complete_data, data])
    return complete_data

def process_curated_file(path, animal_list_path, day_start="06:00", day_end="18:00"):
    # This function processes a curated excel file and converts it
    # into a pandas DataFrame for further processing
    #
    # Parameters:
    #
    # path - string; Defines the Excel file with the curated data
    # animal_list_path - string; Gives the path+filename for the animal list

    # Load animal list
    animal_list = pd.read_excel(animal_list_path, header=0)

    # Load curated dataset
    data = pd.read_excel(path)

    # Rename column names. This might need adjustment if the column structure is different in other curated datasets
    data = data.rename(columns={"Time": "time", "Systolic": "systolic", "MAP": "map", "Heart Rate": "hr",
                                "Diastolic": "diastolic", "Activity": "activity", "ID": "animal", "Group": "group"})

    # Round time values to full minutes. This is to get rid of the time points
    # which are - for whatever reason - not full minutes
    data["time"] = data.time.dt.round("min")

    complete_data = pd.DataFrame() # This DataFrame will contain all data in the end

    # Now process all animals from the list
    for animal in data.animal.unique():
        animal_data = data[data.animal == animal]
        rel_time_offset = 0 # animal_list[animal_list["Animal_ID"] == animal].rel_offset.values[0]
        animal_data = animal_data.dropna()
        # Add a time stamp relative to the start of the experiment
        animal_data["rel_time"] = animal_data.time - animal_data.time.iloc[0]
        animal_data["rel_time"] = animal_data["rel_time"].astype("timedelta64[m]")/(24*60)



        animal_data["night"] = 1
        animal_data.index = animal_data.time
        animal_data.iloc[
            animal_data.index.indexer_between_time(day_start, day_end, include_start=True, include_end=True),
            animal_data.columns.get_loc('night')] = 0
        animal_data["time_of_day"] = animal_data["time"].dt.time

        complete_data = pd.concat([complete_data, animal_data])

    return complete_data


def plot_mean_per_group(data, pdf, group_list, ylim=(None, None)):
    # This function plots the mean of every group
    #
    # Parameters:
    #
    # data - DataFrame; Contains all blood pressure data
    # pdf - matplotlib.PDFPages object; Allows to save graphs into PDF
    # group_list - list of strings; Contains all groups that should be analyzed
    # ylim - set of two values (default = None); This set defines the y-axis scaling while the value will be
    #        automatically determined if set to "None"

    number_of_groups = len(group_list)

    plt.figure(figsize=(10, 2 * number_of_groups))  # Create figure

    for i, group in enumerate(group_list):
        plt.subplot(number_of_groups, 1, i + 1)  # Create subplot based on the number of groups

        data_subset = data[data.group == group]
        data_subset.groupby("rel_time").mean().map.dropna().plot(color="black", lw=0.5, label="MAP")
        data_subset.groupby("rel_time").mean().systolic.dropna().plot(color="red", lw=0.2, alpha=0.5,
                                                                      label="Systolic")
        data_subset.groupby("rel_time").mean().diastolic.dropna().plot(color="blue", lw=0.2, alpha=0.5,
                                                                       label="Diastolic")
        plt.legend(bbox_to_anchor=(1, 0.5))
        plt.title(f"Mean raw values of {group}")
        plt.ylabel("Pressure (mmHg)")
        plt.xlabel("")
        plt.ylim(ylim)

    plt.xlabel("Days")
    plt.tight_layout()
    pdf.savefig()


def plot_animal(data, pdf, animal_list, xlim=(None, None), ylim_bp=(None, None), ylim_amp=(None, None),
                ylim_hr=(None, None), ylim_activity=(None, None)):
    # This function plots the values for every individual animal
    #
    # Parameters:
    #
    # data - DataFrame; Contains all blood pressure data
    # pdf - matplotlib.PDFPages object; Allows to save graphs into PDF
    # animal - list of strings; Contains all animals that should be analyzed
    # xlim - set of two values (default = None); This set defines the x-axis scaling while the value will be
    #       automatically determined if set to "None"
    # ylim_bp, ylim_amp, ylim_hr and ylim_activity - set of two values each (default = None); These sets define the
    #       y-axis scaling for the different subplots (blood pressure, amplitude, heart rate and activity), respectively

    for animal in animal_list:
        plt.figure(figsize=(10, 8))  # Create figure

        animal_data = data[data.animal == animal]  # Create subset of data for an individual animal

        # There will be four subplots: systolic/diastolic/MAP, BP amplitude, heart rate and activity

        # First subplot of the systolic, diastolic and MAP values
        plt.subplot(411)
        plt.plot(animal_data["rel_time"], animal_data["systolic"], color="red", lw=0.5, alpha=0.5,
                 label="Systolic")  # Plot systolic blood pressure
        plt.plot(animal_data["rel_time"], animal_data["diastolic"], color="blue", lw=0.5, alpha=0.5,
                 label="Diastolic")  # Plot diastolic blood pressure
        plt.plot(animal_data["rel_time"], animal_data["map"], color="black", lw=0.5, label="MAP")  # Plot MAP

        plt.title(f"Group: {animal_data.group.unique()[0]}, Animal: {animal}")
        plt.ylabel("Pressure (mmHg)")
        plt.ylim(ylim_bp)
        plt.xlim(xlim)
        limits = plt.gca().get_xlim()
        plt.xticks(range(int(limits[0]), int(limits[1]), 1), rotation=45)
        plt.grid(visible=True, which="both", axis="x")

        plt.legend()
        # Second subplot of the blood pressure amplitude (sys.-dia.)
        plt.subplot(412)
        plt.plot(animal_data["rel_time"], animal_data["systolic"] - animal_data["diastolic"],
                 color="orange", lw=0.5, label="Blood Pressure Amplitude")

        plt.ylabel("Pressure \nAmplitude (mmHg)")

        plt.ylim(ylim_amp)
        plt.xlim(xlim)
        plt.xticks(range(int(limits[0]), int(limits[1]), 1), rotation=45)
        plt.grid(visible=True, which="both", axis="x")

        plt.legend()

        # Third subplot of the heart rate
        plt.subplot(413)
        plt.plot(animal_data["rel_time"], animal_data["hr"], color="green", lw=0.5, label="Heart Rate")

        plt.ylabel("Beats per minute")

        plt.ylim(ylim_hr)
        plt.xlim(xlim)
        plt.xticks(range(int(limits[0]), int(limits[1]), 1), rotation=45)
        plt.grid(visible=True, which="both", axis="x")

        plt.legend()

        # Fourth subplot of the activity
        plt.subplot(414)
        plt.plot(animal_data["rel_time"], animal_data["activity"], color="blue", lw=0.5, label="Activity")
        plt.ylabel("Activity (a.u.)")
        plt.xlabel("Days")

        plt.ylim(ylim_activity)
        plt.xlim(xlim)
        plt.xticks(range(int(limits[0]), int(limits[1]), 1), rotation=45)
        plt.grid(visible=True, which="both", axis="x")

        plt.legend()

        pdf.savefig()


def main():
    # This function contains all stuff for handling the graphical user interface

    raw_layout = [
        [sg.Text("Scan files in directory:")],
        [sg.Input(key="-DIRECTORY-",
                  default_text=""),
         sg.FolderBrowse('Select input directory...', target='-DIRECTORY-')],
        [sg.Text("Animal list")],
        [sg.Input(key="-ANIMAL_LIST-", default_text=""),
         sg.FileBrowse('Select animal list...', target='-ANIMAL_LIST-')],
        [sg.Text("PDF Output")],
        [sg.Input(key="-PDF_FILE-", default_text=""),
         sg.FileSaveAs('Save as PDF file...', target='-PDF_FILE-')],
        [sg.Button("Start processing raw files")],
    ]

    curated_layout = [
        [sg.Text("Excel file with curated data:")],
        [sg.Input(key="-CURATED_FILE-", default_text=""), sg.FileBrowse('Select file', target='-CURATED_FILE-')],
        [sg.Text("Animal list")],
        [sg.Input(key="-ANIMAL_LIST-", default_text=""),
         sg.FileBrowse('Select animal list...', target='-ANIMAL_LIST-')],
        [sg.Text("PDF Output")],

        [sg.Input(key="-PDF_FILE-", default_text=""),
         sg.FileSaveAs('Save as PDF file...', target='-PDF_FILE-')],
        [sg.Button("Start processing curated file")],
    ]
    layout = [
        [sg.TabGroup([[sg.Tab('Explore raw data', raw_layout), sg.Tab('Explore curated data', curated_layout)]])],
        [sg.Button('Exit')],
    ]

    #sg.Print("ExploreBP - Output", do_not_reroute_stdout=False)
    window = sg.Window("ExploreBP", layout)

    while True:
        event, values = window.read()  # Read the event that happened and the values dictionary
        # print(event, values)
        # If user closed window with X or if user clicked "Exit" button then exit
        if event == sg.WIN_CLOSED or event == "Exit":
            break
        if event == 'Start processing raw files':
            if values["-DIRECTORY-"] and values["-ANIMAL_LIST-"] and values["-PDF_FILE-"]:
                # Select the folder containing the raw files
                bp_data = process_raw_directory(values["-DIRECTORY-"], values["-ANIMAL_LIST-"])
                with PdfPages(values["-PDF_FILE-"]) as pdf:
                    plot_mean_per_group(bp_data, pdf, bp_data.group.unique())
                    plot_animal(bp_data, pdf, bp_data.sort_values(by="group").animal.unique())
        if event == 'Start processing curated file':
            if values["-CURATED_FILE-"] and values["-ANIMAL_LIST-"] and values["-PDF_FILE-"]:
                # Select the folder containing the raw files
                bp_data = process_curated_file(values["-CURATED_FILE-"], values["-ANIMAL_LIST-"])
                with PdfPages(values["-PDF_FILE-"]) as pdf:
                    plot_mean_per_group(bp_data, pdf, bp_data.group.unique())
                    plot_animal(bp_data, pdf, bp_data.sort_values(by="group").animal.unique())

    window.close()


# This loop will be run upon the start of the program
if __name__ == '__main__':
    main()
