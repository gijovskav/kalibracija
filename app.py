import streamlit as st
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
import io
from io import BytesIO


df_std = None
df_blank_processed = None
sample_tables = []
summary = None

st.title("Брза калибрација")

std_dataframes = []
df_blank_results = pd.DataFrame()
df_samples_results = pd.DataFrame()



# --- Избор на методи ---
st.markdown("### Избери една или повеќе методи за калибрација:")
method_one_point = st.checkbox("Калибрација со една точка")
method_internal_curve = st.checkbox("Калибрација со калибрациона права со внатрешен стандард")
method_external_curve = st.checkbox("Калибрација со надворешна калибрациона права")

# --- Заеднички полиња ---
st.markdown("### Проби за анализа")
blank_file = st.file_uploader("Прикачи blank (.xlsx)", type=["xls", "xlsx"])
sample_files = st.file_uploader("Прикачи samples (.xlsx)", type=["xls", "xlsx"], accept_multiple_files=True)
v_extract = st.number_input("Волумен на конечен екстракт (mL)", min_value=0.0, format="%.2f", key="v_extract")

# --- ако е потребен IS ---
if method_one_point or method_internal_curve:
    st.markdown("### Внеси податоци за внатрешен стандард ")
    is_name = st.text_input("Име на внатрешен стандард (како во Excel)", key="is_name")

 # --- Метод 1: Една точка ---
if method_one_point:
    st.markdown("### Параметри за метода: Калибрација со една точка")
    c_is_start = st.number_input("Почетна концентрација на IS (µg/L)", min_value=0.0, format="%.3f", key="c_is_start")

    st.markdown("#### Прикачи стандард за калибрација со една точка:")
    std_file_one_point = st.file_uploader("Стандард (1 документ)", type=["xls", "xlsx"], key="onep_file")
    conc_one_point = st.number_input("Концентрација на Стандардот (µg/L)", min_value=0.0, format="%.3f", key="onep_conc")


        # --- Метод 2: Внатрешна калибрациона крива ---
if method_internal_curve:
    st.markdown("### Параметри за метода: Калибрациона права со внатрешен стандард")
    c_is_extract = st.number_input("Концентрација на IS во екстракт (µg/L)", min_value=0.0, format="%.3f", key="c_is_extract")


      # --- Серија на стандарди (една за сите методи што ја користат) ---
if method_internal_curve or method_external_curve or (method_one_point and (method_internal_curve or method_external_curve)):
    st.markdown("### Серија на стандарди за калибрациона крива")


    # Барање број на стандарди само еднаш
    num_standards = st.number_input("Колку стандарди ќе користите? Ако користите метода на калибрациона права со внатрешен стандард прв ставете го референтниот стандард", min_value=1, max_value=20, value=5, step=1)

    uploaded_std_files = []
    std_concentrations = []
    std_dataframes = []

    # Ако корисникот избрал број на стандарди > 0, прикажи полета за внес
    if num_standards > 0:
        for i in range(num_standards):
            cols = st.columns(2)
            with cols[0]:
                file = st.file_uploader(f"Стандард {i+1} – Excel фајл", type=["xls", "xlsx"], key=f"std_file_{i}")
                uploaded_std_files.append(file)
            with cols[1]:
                conc = st.number_input(f"Концентрација за стандард {i+1} (µg/L)", min_value=0.0, format="%.4f", key=f"std_conc_{i}")
                std_concentrations.append(conc)


# --- Крај ---
st.markdown("---")
st.success("Внеси ги сите потребни податоци според избраните методи.")


# PRVA METODA
if method_one_point:
    def find_column(df, possible_names):
        """Наоѓа колона во df според листа на можни имиња."""
        for name in possible_names:
            if name in df.columns:
                return name
        return None

    if std_file_one_point is not None:
        # Читање на Excel со стандарден документ
        df_std = pd.read_excel(std_file_one_point)

        # Наоѓање на колони
        name_col = find_column(df_std, ["Name", "name", "NAME"])
        rt_col = find_column(df_std, ["RT","RT (min)", "Retention Time", "retention time", "rt"])
        height_col = find_column(df_std, ["Height", "Height (Hz)", "height", "height (Hz)"])

        if None in (name_col, rt_col, height_col):
            st.error("Не можам да ги најдам потребните колони во стандарден документ.")
        else:
            # Бараме висина на IS
            is_mask = df_std[name_col].astype(str) == is_name
            if not is_mask.any():
                st.error(f"Внатрешниот стандард '{is_name}' не е пронајден во стандарден документ.")
            else:
                height_is = df_std.loc[is_mask, height_col].values[0]
                # Пресметка на RRF
                df_std['RRF'] = df_std.apply(
                    lambda row: (row[height_col] / height_is) * (c_is_start / conc_one_point)
                    if row[name_col] != is_name else 1.0,
                    axis=1
                )

                # Создавање на реден број
                df_std.insert(0, "Ред. бр.", range(1, len(df_std) + 1))

                # Промена на имиња на колоните за подобар приказ
                df_std = df_std.rename(columns={
                    name_col: "Name",
                    rt_col: "RT (min)",
                    height_col: "Height (Hz)"
                })

                st.markdown("### Табела со RRF:")
                st.dataframe(df_std[["Ред. бр.", "Name", "RT (min)", "Height (Hz)", "RRF"]])

    def normalize_columns(df):
        # Препознавање на колона за Name
        name_cols = [col for col in df.columns if col.strip().lower() in ['name', 'compound']]

        # Препознавање на RT колона
        rt_cols = [col for col in df.columns if any(x in col.lower() for x in ['rt (min)', 'rt'])]

        # Препознавање на Height колона
        height_cols = [col for col in df.columns if 'height' in col.lower()]

        norm_df = pd.DataFrame()

        # Избор на соодветни колони, ако се најдени
        norm_df['Name'] = df[name_cols[0]] if name_cols else None
        norm_df['RT (min)'] = df[rt_cols[0]] if rt_cols else None
        norm_df['Height (Hz)'] = df[height_cols[0]] if height_cols else None

        return norm_df

    def process_sample(df_sample, df_std, c_is_start, v_extract, is_name):
        # Наоѓање на IS висина во sample
        is_mask_sample = df_sample['Name'].astype(str) == is_name
        if not is_mask_sample.any():
            st.error(f"Внатрешниот стандард '{is_name}' не е пронајден во sample документ.")
            return None
        
        height_is_sample = df_sample.loc[is_mask_sample, 'Height (Hz)'].values[0]

        # Генерира реден број
        df_sample.insert(0, "Ред. бр.", range(1, len(df_sample) + 1))

        # Наоѓање RRF од стандарди според Name
        def get_rrf(name):
            match = df_std[df_std['Name'] == name]
            if not match.empty:
                return match['RRF'].values[0]
            else:
                return None

        df_sample['RRF'] = df_sample['Name'].apply(get_rrf)

        # Пресметка на c(X)
        df_sample['c(X) / µg L-1'] = df_sample.apply(lambda row: 
            (row['Height (Hz)'] / height_is_sample) * (c_is_start / row['RRF']) 
            if row['RRF'] else None, axis=1)

        # Пресметка на маса во ng
        df_sample['Маса (ng)'] = df_sample['c(X) / µg L-1'] * v_extract

        return df_sample[['Ред. бр.', 'Name', 'RT (min)', 'Height (Hz)', 'RRF', 'c(X) / µg L-1', 'Маса (ng)']]

       # --- Пример за blank обработка ---
    if blank_file is not None:
        blank_df = pd.read_excel(blank_file)
        df_blank_processed = process_sample(blank_df, df_std, c_is_start, v_extract, is_name)
        if df_blank_processed is not None:
            st.markdown("### Калибрација со една точка - Blank:")
            st.dataframe(df_blank_processed)

    # --- Пример за samples обработка ---
    sample_tables = []
    for idx, sample_file in enumerate(sample_files):
        sample_df = pd.read_excel(sample_file)
        df_sample_processed = process_sample(sample_df, df_std, c_is_start, v_extract, is_name)
        if df_sample_processed is not None:
            st.markdown(f"### Калибрација со една точка - Sample {idx + 1}:")
            st.dataframe(df_sample_processed)
            sample_tables.append(df_sample_processed)

    # --- Сумарна табела со сите соединенија и маси во blank и samples ---
    if df_blank_processed is not None and sample_tables:
        summary = df_blank_processed[['Name', 'Маса (ng)']].rename(columns={'Маса (ng)': 'Маса (ng) Blank'})
        for i, df_sample_proc in enumerate(sample_tables):
            summary = summary.merge(df_sample_proc[['Name', 'Маса (ng)']].rename(columns={'Маса (ng)': f'Маса (ng) Sample {i + 1}'}),
                                    on='Name', how='outer')
        summary = summary.fillna(0)

        st.markdown("### Калибрација со една точка - сумарна табела:")
        st.dataframe(summary)

    if std_file_one_point is not None and df_std is not None:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Табела со стандардниот документ
            df_std.to_excel(writer, sheet_name="RRFs", index=False)

            # Blank табела
            if df_blank_processed is not None:
                df_blank_processed.to_excel(writer, sheet_name="Blank", index=False)

            # Samples табели
            for i, df_sample_proc in enumerate(sample_tables):
                df_sample_proc.to_excel(writer, sheet_name=f"Sample {i + 1}", index=False)

            # Сумирана табела
            if df_blank_processed is not None and sample_tables:
                summary.to_excel(writer, sheet_name="Сумирано", index=False)

        st.download_button(
            label="⬇️ Преземи ги резултатите во Excel - Калибрација со една точка",
            data=output.getvalue(),
            file_name="kalibracija_edna_tocka.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )




#ako e vnesena serija standardi
if method_internal_curve or method_external_curve:
    for file in uploaded_std_files:
        if file is not None:
            df = pd.read_excel(file)
            std_dataframes.append(df)
def get_column_name(possible_names, columns):
    for name in possible_names:
        if name in columns:
            return name
    return None

if std_dataframes:
    df_reference = std_dataframes[0].copy()
    cols = df_reference.columns

    name_col = get_column_name(["Name", "name"], cols)
    rt_col = get_column_name(["RT (min)", "RT", "rt"], cols)
    height_col_base = get_column_name(["Height (Hz)", "Height", "height"], cols)

    if name_col and rt_col and height_col_base:
        result_df = df_reference[[name_col, rt_col]].copy()
        result_df.rename(columns={name_col: "Name", rt_col: "RT"}, inplace=True)

        for i, df_std in enumerate(std_dataframes):
            height_col = get_column_name(["Height (Hz)", "Height", "height"], df_std.columns)
            name_col_std = get_column_name(["Name", "name"], df_std.columns)

            if height_col and name_col_std:
                df_merge = df_std[[name_col_std, height_col]].copy()
                df_merge.rename(columns={
                    name_col_std: "Name",
                    height_col: f"Height_{i + 1}"
                }, inplace=True)

                result_df = result_df.merge(df_merge, on="Name", how="left")
            else:
                st.warning(f"⚠️ Стандард {i + 1} нема 'Name' и/или 'Height' колони.")

        st.write("### Собрани висини од сите стандарди:")
        st.dataframe(result_df)
    else:
            st.warning("⛔ Првиот стандард мора да ги содржи колоните: Name или name, Height (Hz), height, или Height и RT или RT(min)")

#EKSTERNA KALIBRACIJA
if method_external_curve and 'result_df' in locals() and result_df is not None and std_concentrations:
    calibration_data = []

    X_full = np.array(std_concentrations).reshape(-1, 1)

    df_blank_processed = None
    if blank_file is not None:
        df_blank_processed = pd.read_excel(blank_file)

    sample_tables = []
    if sample_files:
        for f in sample_files:
            sample_tables.append(pd.read_excel(f))






        # Филтрирање на колоните што се само Height_X
        height_columns = [col for col in result_df.columns if col.startswith("Height_")]

        for index, row in result_df.iterrows():
            name = row["Name"]
            heights = row[height_columns].values

            # Комбинирај ги само валидните парови
            valid_pairs = [(x, y) for x, y in zip(std_concentrations, heights) if pd.notna(y)]

            if len(valid_pairs) < 2:
                continue

            x_vals, y_vals = zip(*valid_pairs)
            X = np.array(x_vals).reshape(-1, 1)
            y = np.array(y_vals).reshape(-1, 1)

            model = LinearRegression()
            model.fit(X, y)

            slope = float(model.coef_)
            intercept = float(model.intercept_)
            r2 = float(model.score(X, y))

            calibration_data.append({
                "Name": name,
                "Slope": slope,
                "Intercept": intercept,
                "Correlation (R²)": r2
            })

        df_calibration = pd.DataFrame(calibration_data)

        if not df_calibration.empty:
            st.write("### Калибрациона права за надворешна калибрација:")
            st.dataframe(df_calibration)
        else:
            st.warning("⚠️ Нема доволно податоци за да се изврши калибрација.")

    else:
        st.warning("Нема податоци за резултат или стандардни концентрации за калкулација.")



    def calculate_concentration_and_mass(df, df_calib, v_extract):
        df_result = df.copy()
        df_result["c(X) / µg/L"] = None
        df_result["Маса (ng)"] = None

        for idx, row in df_result.iterrows():
            name = row.get("Name")
            height = row.get("Height") or row.get("Height (Hz)") or row.get("height")

            if pd.isna(height):
                continue

            calib_row = df_calib[df_calib["Name"] == name]
            if not calib_row.empty:
                slope = calib_row["Slope"].values[0]
                intercept = calib_row["Intercept"].values[0]

                if slope != 0:
                    conc = (height - intercept) / slope
                    mass = conc * v_extract

                    df_result.at[idx, "c(X) / µg/L"] = conc
                    df_result.at[idx, "Маса (ng)"] = mass

        return df_result


    # Пресметка за blank
    blank_final = None
    if df_blank_processed is not None and not df_calibration.empty:
        blank_final = calculate_concentration_and_mass(df_blank_processed, df_calibration, v_extract)
        st.markdown("### Надворешна калибрациона - Blank:")
        st.dataframe(blank_final)

    # Пресметка за samples
    samples_final = []
    if sample_tables and not df_calibration.empty:
        for df_sample in sample_tables:
            sample_calc = calculate_concentration_and_mass(df_sample, df_calibration, v_extract)
            samples_final.append(sample_calc)
            st.markdown(f"### Надворешна калибрациона - Sample {len(samples_final)} :")
            st.dataframe(sample_calc)

    # Сумирана табела
    if blank_final is not None and samples_final:
        all_names = set(blank_final["Name"].unique())
        for df_s in samples_final:
            all_names.update(df_s["Name"].unique())

        summary_data = []
        for name in all_names:
            row = {"Name": name}
            blank_mass = blank_final[blank_final["Name"] == name]["Маса (ng)"].sum()
            row["Blank"] = blank_mass
            for i, df_s in enumerate(samples_final):
                sample_mass = df_s[df_s["Name"] == name]["Маса (ng)"].sum()
                row[f"Sample {i + 1}"] = sample_mass
            summary_data.append(row)

        df_summary = pd.DataFrame(summary_data)

        st.markdown("### Надворешна калибрациона - сумирано:")
        st.dataframe(df_summary)

        # Генерирање Excel со сите резултати
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            blank_final.to_excel(writer, sheet_name="Blank", index=False)
            for i, df_s in enumerate(samples_final):
                df_s.to_excel(writer, sheet_name=f"Sample {i + 1}", index=False)
            df_summary.to_excel(writer, sheet_name="Сумирано", index=False)
        output.seek(0)

        st.download_button(
            label="⬇️ Симни ги резултатите во ексел - надворешна калибрациона",
            data=output,
            file_name="nadvoresna_kalibraciona.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("Не може да се генерира сумарна табела поради недостасувачки резултати за blank или samples.")



# INTERNA
# Осигурај се дека result_df и std_concentrations се дефинирани
if 'result_df' not in locals():
    result_df = None
if 'std_concentrations' not in locals():
    std_concentrations = []

# Внатрешна калибрација со крива - извршување само ако се вклучи оваа опција
if method_internal_curve and result_df is not None and std_concentrations:

    # 1. Пресметај C(X)/C(IS) регресија базирана на H(X)/H(IS)
    std_conc_norm = np.array(std_concentrations) / std_concentrations[0]
    std_conc_norm = std_conc_norm.reshape(-1, 1)

    # Подготви ratio_df = H(X)/H(IS) за секој стандард
    ratio_df = result_df[["Name"]].copy()
    height_cols = [col for col in result_df.columns if col.startswith("Height_")]

    for idx, col in enumerate(height_cols):
        df_std = std_dataframes[idx]  # земи го соодветниот стандард
        is_row = df_std[df_std[name_col] == is_name]

        if not is_row.empty:
            is_height = is_row[height_col_base].values[0]
            if pd.notna(is_height) and is_height != 0:
                ratio_df[f"Ratio_{col.split('_')[-1]}"] = result_df[col] / is_height
            else:
                st.warning(f"⚠️ Висината за IS ({is_name}) во стандард {idx+1} не е валидна: {is_height}")
                ratio_df[f"Ratio_{col.split('_')[-1]}"] = np.nan
        else:
            st.warning(f"⚠️ IS '{is_name}' не е пронајден во стандард {idx+1}.")
            ratio_df[f"Ratio_{col.split('_')[-1]}"] = np.nan

    # Ако успешно се пресметани односите, продолжи со регресија
    if ratio_df is not None:
        regression_results = []

        for idx, row in ratio_df.iterrows():
            name = row["Name"]
            ratios = [row.get(f"Ratio_{i+1}", np.nan) for i in range(len(std_concentrations))]

            if pd.isna(ratios).any():
                continue

            y_vals = np.array(ratios).reshape(-1, 1)
            model = LinearRegression()
            model.fit(std_conc_norm, y_vals)

            slope = float(model.coef_)
            intercept = float(model.intercept_)
            correl = float(np.corrcoef(std_conc_norm.flatten(), y_vals.flatten())[0, 1])

            regression_results.append({
                "Name": name,
                "H(X)/H(IS)": "; ".join([f"{r:.3f}" for r in ratios]),
                "c(X)/c(IS)": f"{slope:.6f}",
                "Intercept": f"{intercept:.6f}",
                "Correlation": f"{correl:.4f}"
            })

        df_c_over_cis = pd.DataFrame(regression_results)
        st.write("df_c_over_cis preview:", df_c_over_cis.head())

        st.markdown("### Внатрешна калибрациона права")
        st.dataframe(df_c_over_cis)

        # 2. Примени ги регресиите на бланкови и семплови
        all_samples = []

        if blank_file is not None:
            df_blank = pd.read_excel(blank_file)
            df_blank["Sample ID"] = "Blank"
            all_samples.append(df_blank)

        if sample_files:
            for idx, f in enumerate(sample_files):
                df_sample = pd.read_excel(f)
                df_sample["Sample ID"] = f"Sample_{idx+1}"
                all_samples.append(df_sample)

        df_all_samples = pd.concat(all_samples, ignore_index=True)

        blank_results = []
        samples_results = []

        for sample_id in df_all_samples["Sample ID"].unique():
            df_current = df_all_samples[df_all_samples["Sample ID"] == sample_id]
            is_row = df_current[df_current[name_col] == is_name]

            if is_row.empty:
                st.warning(f"⚠️ IS '{is_name}' не е пронајден во {sample_id}.")
                continue

            is_height_sample = is_row[height_col_base].values[0]
            if pd.isna(is_height_sample) or is_height_sample == 0:
                st.warning(f"⚠️ Висината за IS во {sample_id} не е валидна.")
                continue

            for _, analyte_row in df_current.iterrows():
                compound_name = analyte_row[name_col]
                if compound_name == is_name:
                    continue

                analyte_height = analyte_row[height_col_base]
                if pd.isna(analyte_height):
                    continue

                hx_over_his = analyte_height / is_height_sample
                row_reg = df_c_over_cis[df_c_over_cis["Name"] == compound_name]

                if row_reg.empty:
                    continue

                slope = float(row_reg["c(X)/c(IS)"].values[0])
                intercept = float(row_reg["Intercept"].values[0])

                cx_over_cis = (hx_over_his - intercept) / slope
                cx = cx_over_cis * c_is_extract
                final_amt = cx * v_extract

                row_result = {
                    "Name": compound_name,
                    "H(X)/H(IS)": hx_over_his,
                    "C(X)/C(IS)": cx_over_cis,
                    "C(X)": cx,
                    "Маса (ng)": final_amt
                }

                if sample_id == "Blank":
                    blank_results.append(row_result)
                else:
                    row_result["Sample ID"] = sample_id
                    samples_results.append(row_result)

        df_blank_results = pd.DataFrame(blank_results)
        df_samples_results = pd.DataFrame(samples_results)

        if df_blank_results.empty or df_samples_results.empty:
            st.warning("DataFrames се празни, проверете влезните податоци.")
    
        st.markdown("### Внатрешна калибрациона - Blank")
        st.dataframe(df_blank_results)

        st.markdown("### Внатрешна калибрациона - Samples")
        st.dataframe(df_samples_results)

        # Сумирана табела: секој sample посебна колона
        # Заштита од празни или невалидни DataFrame-и
        if df_blank_results.empty or df_samples_results.empty:
            st.warning("Blank или Sample резултатите се празни - прикачи фајлови.")
        else:
            if "Name" in df_blank_results.columns and "Name" in df_samples_results.columns:
                all_names = set(df_blank_results["Name"].unique()) | set(df_samples_results["Name"].unique())
                sample_ids = df_samples_results["Sample ID"].unique()

                summary_rows = []

                for name in sorted(all_names):
                    row = {"Name": name}

                    # Blank
                    blank_mass = df_blank_results[df_blank_results["Name"] == name]["Маса (ng)"].sum()
                    row["Blank"] = blank_mass

                    # Секој sample
                    for sid in sample_ids:
                        val = df_samples_results[
                            (df_samples_results["Name"] == name) & 
                            (df_samples_results["Sample ID"] == sid)
                        ]["Маса (ng)"].sum()
                        row[sid] = val

                    summary_rows.append(row)

                df_summary = pd.DataFrame(summary_rows)

                st.markdown("### Внатрешна калибрациона - сумирано")
                st.dataframe(df_summary)

                # Генерирај Excel
                output_excel = io.BytesIO()
                with pd.ExcelWriter(output_excel, engine="openpyxl") as writer:
                    df_blank_results.to_excel(writer, sheet_name="Blank", index=False)
                    df_samples_results.to_excel(writer, sheet_name="Samples", index=False)
                    df_summary.to_excel(writer, sheet_name="Summary", index=False)
                output_excel.seek(0)

                st.download_button(
                    label="💾 Симни резултати - внатрешна калибрациона",
                    data=output_excel.getvalue(),
                    file_name="vnatresna_kalibraciona.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("❌ Недостасува колоната 'Name' во некој од резултатите.")
                



#krajna tabela
# --- Безбедно земање имиња од стандард ---
std_names = []

if method_one_point and not (method_internal_curve or method_external_curve):
    if 'df_std' in locals() and isinstance(df_std, pd.DataFrame) and 'Name' in df_std.columns:
        df_std['Name'] = df_std['Name'].astype(str).str.strip().str.lower()
        std_names = df_std['Name'].dropna().unique().tolist()
else:
    combined_std_df = pd.concat(std_dataframes, ignore_index=True) if std_dataframes else pd.DataFrame()
    if not combined_std_df.empty and 'Name' in combined_std_df.columns:
        combined_std_df['Name'] = combined_std_df['Name'].astype(str).str.strip().str.lower()
        std_names = combined_std_df['Name'].dropna().unique().tolist()



# --- Почетна табела само со имињата од стандардот ---
df_combined = pd.DataFrame({'Name': sorted(std_names)})

# --- Проверка и подготовка на табелите од методите ---
dfs_to_merge = []

def normalize_name_column(df):
    df = df.copy()
    if 'Name' in df.columns:
        df['Name'] = df['Name'].astype(str).str.strip().str.lower()
    return df

# One Point Method
summary = locals().get('summary')
if isinstance(summary, pd.DataFrame) and not summary.empty:
    df_1p = normalize_name_column(summary)
    df_1p = df_1p.rename(columns=lambda c: f"{c} (One Point)" if c != 'Name' else c)
    dfs_to_merge.append(df_1p)

# Internal Curve
df_summary = locals().get('df_summary')
if isinstance(df_summary, pd.DataFrame) and not df_summary.empty:
    df_internal = normalize_name_column(df_summary)
    df_internal = df_internal.rename(columns=lambda c: f"{c} (Internal Curve)" if c != 'Name' else c)
    dfs_to_merge.append(df_internal)

# External Curve
df_summary_external = locals().get('df_summary_external')
if isinstance(df_summary_external, pd.DataFrame) and not df_summary_external.empty:
    df_external = normalize_name_column(df_summary_external)
    df_external = df_external.rename(columns=lambda c: f"{c} (External Curve)" if c != 'Name' else c)
    dfs_to_merge.append(df_external)

# --- Спојување само според стандардните имиња ---
for df_method in dfs_to_merge:
    df_combined = df_combined.merge(df_method, on='Name', how='left')

# --- Пополнување празни вредности со 0 ---
df_combined = df_combined.fillna(0)

# --- Прикажи резултат ---
st.markdown("### Комбинирана сумирана табела за сите методи и samples:")
st.dataframe(df_combined)




#odzemanja
import re

# --- Помошна функција: нормализирање ---
def normalize(df, method_label):
    df = df.copy()
    df['Name'] = df['Name'].astype(str).str.strip().str.lower()
    df = df.rename(columns={col: f"{col} ({method_label})" for col in df.columns if col != 'Name'})
    return df

# --- Главна функција: корекција по метод со сопствен blank ---
def correct_by_individual_blank(df_method, method_label):
    df_method = normalize(df_method, method_label)
    val_col = [col for col in df_method.columns if col != 'Name'][0]

    corrected_rows = []

    for idx, row in df_method.iterrows():
        name = row['Name']
        
        # Skip blank rows
        if re.search(r'\b(blank|слепа)\b', name, flags=re.IGNORECASE):
            continue

        # Tentaive blank name (tries to match with corresponding blank)
        possible_blank_names = [
            f"blank {name}", f"слепа {name}", f"{name} blank", f"{name} слепа"
        ]

        blank_row = df_method[df_method['Name'].isin(possible_blank_names)]

        if not blank_row.empty:
            blank_val = blank_row.iloc[0][val_col]
        else:
            blank_val = 0  # ако нема blank за овој sample

        corrected_val = row[val_col] - blank_val

        corrected_rows.append({'Name': name, f"{val_col} (corrected)": corrected_val})

    return pd.DataFrame(corrected_rows)

# --- Собери ги сите методи и обработи ги одделно ---
final_tables = []

if isinstance(summary, pd.DataFrame) and not summary.empty:
    corrected_1p = correct_by_individual_blank(summary, "One Point")
    final_tables.append(corrected_1p)

if isinstance(df_summary, pd.DataFrame) and not df_summary.empty:
    corrected_internal = correct_by_individual_blank(df_summary, "Internal Curve")
    final_tables.append(corrected_internal)

if isinstance(df_summary_external, pd.DataFrame) and not df_summary_external.empty:
    corrected_external = correct_by_individual_blank(df_summary_external, "External Curve")
    final_tables.append(corrected_external)

# --- Спојување на сите во една табела по Name ---
from functools import reduce
df_final = reduce(lambda left, right: pd.merge(left, right, on='Name', how='outer'), final_tables)

# --- Сортирање и пополнување празни вредности ---
df_final = df_final.fillna(0)
df_final = df_final.sort_values('Name').reset_index(drop=True)

# --- Приказ ---
st.markdown("### Финална компаративна табела со одземени индивидуални слепи проби:")
st.dataframe(df_final)
