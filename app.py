import streamlit as st
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
import io
from io import BytesIO
import re

# --- Глобален избор за број на децимали ---
decimals = st.number_input(
    "Број на децимални места за резултати",
    min_value=0, max_value=6, value=2, step=1,
    key="decimals"
)

# --- Универзална функција за заокружување и заменување None/NaN ---
def round_and_flag(df, decimals):
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df
    out = df.copy()
    num_cols = out.select_dtypes(include=[np.number]).columns
    if len(num_cols):
        out[num_cols] = out[num_cols].round(decimals)
    out = out.replace({None: np.nan})
    out = out.where(pd.notna(out), "Not detected")
    return out


# --- Поставки и празни структури ---
df_std = None
df_blank_processed = None
sample_tables = []
summary = None
std_dataframes = []
df_blank_results = pd.DataFrame()
df_samples_results = pd.DataFrame()

st.title("Брза калибрација")

# --- Избор на методи ---
st.markdown("### Изберете методи за калибрација:")
method_one_point = st.checkbox("Калибрација со внатрешен стандард (една точка)")
method_internal_curve = st.checkbox("Калибрациона права со внатрешен стандард")
method_external_curve = st.checkbox("Надворешна калибрациона права")

# --- Влезни податоци ---
st.markdown("### Влезни податоци за анализа")
blank_file = st.file_uploader("Слепа проба", type=["xls", "xlsx"])
sample_files = st.file_uploader("Примероци за анализа", type=["xls", "xlsx"], accept_multiple_files=True)
v_extract = st.number_input("Волумен на конечен екстракт (mL)", min_value=0.0, format="%.1f", key="v_extract")

# --- Именување на примероци ---
sample_mapping = {}
if sample_files:
    st.markdown("### Именување")
    mapping_data = []
    for idx, file in enumerate(sample_files):
        default_id = f"Примерок {idx+1}"
        filename = file.name
        custom_name = st.text_input(
            f"Корисничко име за {default_id}",
            value=default_id,
            key=f"sample_name_{idx}"
        )
        sample_mapping[filename] = custom_name
        mapping_data.append({
            "Реден број": default_id,
            "Име на датотека": filename,
            "Корисничко име": custom_name
        })
    df_mapping = pd.DataFrame(mapping_data)
    st.dataframe(round_and_flag(df_mapping, decimals))

# --- Помошна функција за добивање име на примерок ---
def get_sample_name(file_name, index):
    return sample_mapping.get(file_name, f"Примерок {index + 1}")


# --- Пресметки ---
presmetaj = st.button("Започни пресметка")
if presmetaj:
    if method_one_point:
        def find_column(df, possible_names):
            for name in possible_names:
                if name in df.columns:
                    return name
            return None

        if 'std_file_one_point' in locals() and std_file_one_point is not None:
            df_std = pd.read_excel(std_file_one_point)
            name_col = find_column(df_std, ["Name", "name", "NAME", "Соединение"])
            rt_col = find_column(df_std, ["RT", "RT (min)", "Retention Time", "Време на задржување"])
            height_col = find_column(df_std, ["Height", "Height (Hz)", "Висина"])

            if None in (name_col, rt_col, height_col):
                st.error("Не се најдени сите потребни колони во документот со стандарди.")
            else:
                is_mask = df_std[name_col].astype(str) == is_name
                if not is_mask.any():
                    st.error(f"Внатрешниот стандард '{is_name}' не е пронајден.")
                else:
                    height_is = df_std.loc[is_mask, height_col].values[0]
                    df_std['RRF'] = df_std.apply(
                        lambda row: (row[height_col] / height_is) * (c_is_start / conc_one_point)
                        if row[name_col] != is_name else 1.0,
                        axis=1
                    )
                    df_std.insert(0, "Ред. бр.", range(1, len(df_std) + 1))
                    df_std = df_std.rename(columns={
                        name_col: "Соединение",
                        rt_col: "RT (min)",
                        height_col: "Висина (Hz)"
                    })
                    st.markdown("### Табела со RRF:")
                    st.dataframe(round_and_flag(df_std[["Ред. бр.", "Соединение", "RT (min)", "Висина (Hz)", "RRF"]], decimals))

    # --- Финални табели секогаш ---
    def normalize_name_column(df):
        df = df.copy()
        if 'Name' in df.columns:
            df = df.rename(columns={'Name': 'Соединение'})
        return df

    available_dfs = []
    if 'summary' in locals() and isinstance(summary, pd.DataFrame) and not summary.empty:
        available_dfs.append((summary, "One Point"))
    if 'df_summary_internal' in locals() and isinstance(df_summary_internal, pd.DataFrame) and not df_summary_internal.empty:
        available_dfs.append((df_summary_internal, "Internal Curve"))
    if 'df_summary_external' in locals() and isinstance(df_summary_external, pd.DataFrame) and not df_summary_external.empty:
        available_dfs.append((df_summary_external, "External Curve"))

    if not available_dfs:
        df_combined = pd.DataFrame({"Соединение": []})
    else:
        first_df = normalize_name_column(available_dfs[0][0])
        df_combined = first_df[["Соединение"]].copy()
        for df_method, method_name in available_dfs:
            df_method = normalize_name_column(df_method)
            numeric_cols = [c for c in df_method.columns if c != "Соединение"]
            for c in numeric_cols:
                df_combined[f"{c} ({method_name})"] = df_method[c].values if len(df_method) == len(df_combined) else 0

    df_combined = df_combined.fillna(0)
    st.markdown("### Финална табела:")
    st.dataframe(round_and_flag(df_combined, decimals))

    # --- Коригирани вредности ---
    df_final = df_combined.copy()
    for col in df_combined.columns:
        if "Слепа проба" in col or "Blank" in col:
            method_match = re.search(r'\((.*?)\)', col)
            if method_match:
                method = method_match.group(1)
                for other_col in df_combined.columns:
                    if other_col != col and f"({method})" in other_col:
                        new_col = other_col.replace(f"({method})", f"- Слепа проба ({method})")
                        df_final[new_col] = df_combined[other_col] - df_combined[col]

    df_final = df_final.fillna(0)
    st.markdown("### Финална табела со коригирани вредности:")
    st.dataframe(round_and_flag(df_final, decimals))

    # --- Реорганизирана табела ---
    df_reorganized = pd.DataFrame()
    if not df_final.empty:
        cols = [c for c in df_final.columns if c != "Соединение"]
        method_map = {}
        for c in cols:
            match = re.search(r"\((.*?)\)", c)
            if match:
                method = match.group(1)
                method_map.setdefault(method, []).append(c)
        ordered_cols = ["Соединение"]
        for m in ["One Point", "Internal Curve", "External Curve"]:
            if m in method_map:
                ordered_cols.extend(method_map[m])
        df_reorganized = df_final[ordered_cols].copy()
    st.markdown("### Табела за споредба на методи:")
    st.dataframe(round_and_flag(df_reorganized, decimals))

    # --- Експорт ---
    def to_excel(dfs: dict, decimals=2):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            for sheet_name, df in dfs.items():
                if isinstance(df, pd.DataFrame) and not df.empty:
                    df_fmt = round_and_flag(df, decimals)
                    df_fmt.to_excel(writer, index=False, sheet_name=sheet_name[:31])
        return output.getvalue()

    dfs_to_export = {
        'Финална табела': df_combined,
        'Коригирана табела': df_final,
        'Реорганизирана табела': df_reorganized
    }

    excel_data = to_excel(dfs_to_export, decimals=decimals)
    st.download_button(
        label="⬇️ Симни ги сите финални табели како Excel",
        data=excel_data,
        file_name='финални_табели.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    



