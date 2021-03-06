from flask import Flask,redirect,url_for

from flask import render_template, request
from app import app
import pymysql as mdb
from .a_Model import *
import pickle
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.metrics.pairwise import linear_kernel
import numpy as np
import base64
db = mdb.connect(user="root", passwd="", host="localhost", db="ghtorrent", charset='utf8')
from github import Github
import time
ACCESS_TOKEN = ''

client = Github(ACCESS_TOKEN, per_page=100)

tfidf_vectorizer = pickle.load(open("/home/ubuntu/Projects/Insight/GitRecruit2/app/training_refined_tfidf_vectorizer_110_6_0.4_1_ALL_cos_1.log","rb"))
tfidf_matrix = pickle.load(open("/home/ubuntu/Projects/Insight/GitRecruit2/app/training_refined_tfidf_matrix_110_6_0.4_1_ALL_cos_1.log","rb"))
ids = pickle.load(open("/home/ubuntu/Projects/Insight/GitRecruit2/app/trainingids.log","rb"))
"""
tfidf_vectorizer = pickle.load(open("/home/ubuntu/Projects/Insight/GitRecruit/app/tfidf_vectorizer.log","rb"))
tfidf_matrix = pickle.load(open("/home/ubuntu/Projects/Insight/GitRecruit/app/tfidf_matrix.log","rb"))
ids = pickle.load(open("/home/ubuntu/Projects/Insight/GitRecruit1/app/ids.log","rb"))
"""
@app.route('/')
def input_f():
  return render_template("input.html")
    
@app.route('/result')
def result():
    method = request.args.get('method')
    repo_name = request.args.get('repo_name')
    print("redirect")
    if method == "repos":

        return redirect(url_for("list_repositories_f",repo_name = repo_name))
    if method == "users":
        if client.rate_limiting[0] < 3:
            return "exceeded API limit"

        repo_name = request.args.get('repo_name')
        try:
            repo = client.get_repo(repo_name)
            
        except Exception:
            return render_template('error.html')
        try:
            readme = repo.get_readme()
            txt = str(base64.b64decode(readme.content))
        except Exception:
            txt = ""
     
        txt = txt.replace("\\n","\n")
        txt = txt.replace("\\t","\t")
        txt = txt.replace("\\r","\n")
        txt = process_text(txt)
        
        if repo.description:
            description = repo.description.replace("\\n","\n")
        else:
            description = ""
        description = description.replace("\\t","\t")
        description = description.replace("\\r","\n")
        description = process_text(description)
        if repo.name:
            name = repo.name.replace("\\n","\n")
        else:
            name = ""
        name = name.replace("\\t","\t")
        name = name.replace("\\r","\n")
        name = process_text(name)
        testing_text = (description+" ")*1+(name+" ")*1+" ".join(txt.split(' ')[:140])
        testing_vector = tfidf_vectorizer.transform([testing_text])
        similarities = cosine_similarity(testing_vector,tfidf_matrix)[0]
#        similarities = linear_kernel(testing_vector,tfidf_matrix)[0]
        sorted_index = np.argsort(-1*similarities)
        sorted_similarities = similarities[sorted_index]
        sorted_ids = np.array(ids)[sorted_index]
        cur = db.cursor()
        cur.execute("SELECT url FROM projects WHERE id="+str(sorted_ids[0])+";")
        query_results = cur.fetchall()
        match = re.search(r"/([^\/]+)/([^\/]+)$",query_results[0][0])
        first_name = match.group(1)+"/"+match.group(2)
        if first_name == repo_name:
            start = 1
        else:
            start = 0
        start = 0
        cut_off = start
        for i in range(start, len(ids)):
            if sorted_similarities[i] < 0.01:
                cut_off = i
                break

        for i in range(start, cut_off):
            cur.execute("SELECT language FROM projects WHERE id="+str(sorted_ids[i])+";")
            query_results = cur.fetchall()
            if repo.language != query_results[0][0]:
                sorted_similarities[i] *= 0.5

        temp_similarities = sorted_similarities[0:cut_off]
        temp_ids = sorted_ids[0:cut_off]
        sorted_index = np.argsort(-1*temp_similarities)
    
        temp_similarities = temp_similarities[sorted_index]
        temp_ids = temp_ids[sorted_index]

        new_cut_off = cut_off

        for i in range(start, cut_off):
            if temp_similarities[i] < 0.01:
                new_cut_off = i
                break


        return_array = []

        for i in range(start,min(10,new_cut_off)):
            cur.execute("SELECT id, name, url, language,description FROM projects WHERE id=%s;" % str(temp_ids[i]))
            query_results = list(cur.fetchall()[0])
            query_results.append(temp_similarities[i])
            query_results[2] = query_results[2].replace('api.','').replace('repos/','')
            return_array.append(query_results)
        cur = db.cursor()

        user_contributions = {}
        user_counts = {}
        for member in return_array:
            key = member[0]
            cur.execute("SELECT id, name, url, language,description FROM projects WHERE id=%s;" % str(key))
            query_results = list(cur.fetchall()[0])
            base_repo_id = query_results[0]
            cur.execute("SELECT DISTINCT COUNT(pull_request_id),head_repo_id FROM pull_requests INNER JOIN  pull_request_history  ON pull_requests.id=pull_request_id  WHERE action='merged' AND base_repo_id = %s GROUP BY head_repo_id;" %str(base_repo_id))
            query_results = list(cur.fetchall())

            for head_repo in query_results:
                if head_repo[1]:
                    cur.execute("SELECT owner_id FROM projects WHERE id=%s;"%head_repo[1])
                    temp_result = cur.fetchall()
                    if temp_result:
                        owner_id = temp_result[0][0]
                        user_counts.setdefault(owner_id,0)
                        user_counts[owner_id] += head_repo[0]
                        user_contributions.setdefault(owner_id,{})
                        user_contributions[owner_id].setdefault(key,0)
                        user_contributions[owner_id][key] += head_repo[0]

    
        output_to_html = []
        for key in sorted(user_contributions.keys(),key = lambda x: -user_counts[x]):
            cur.execute("SELECT id,login,name,email FROM users WHERE id=%s;"%key)
            data_point = cur.fetchall()[0]
            url = "http://github.com/"+data_point[1]
            final_data = data_point+(url,user_counts[key])
            output_to_html.append(final_data)

        return render_template("list_candidates.html", results = output_to_html)


@app.route('/result_query')
def result_query_f():
    method = request.args.get('method')
    query_text = request.args.get('query_text')
    if method == "repos":
        query_text = process_text(query_text)
        print(query_text)
        testing_vector = tfidf_vectorizer.transform([query_text])
        similarities = cosine_similarity(testing_vector,tfidf_matrix)[0]
        sorted_index = np.argsort(-1*similarities)
        sorted_similarities = similarities[sorted_index]
        sorted_ids = np.array(ids)[sorted_index]

        cur = db.cursor()
        start = 0
        cut_off = start
        for i in range(start, len(ids)):
          if sorted_similarities[i] < 0.01:
            cut_off = i
            break
    
        for i in range(start, cut_off):
          cur.execute("SELECT language FROM projects WHERE id="+str(sorted_ids[i])+";")
          query_results = cur.fetchall()
 
        temp_similarities = sorted_similarities[0:cut_off]
        temp_ids = sorted_ids[0:cut_off]
        sorted_index = np.argsort(-1*temp_similarities)
    
        temp_similarities = temp_similarities[sorted_index]
        temp_ids = temp_ids[sorted_index]

        new_cut_off = cut_off

        for i in range(start, cut_off):
          if temp_similarities[i] < 0.01:
            new_cut_off = i
            break


        return_array = []

        for i in range(start,min(new_cut_off,1000)):
          cur.execute("SELECT id, name, url, language,description FROM projects WHERE id=%s;" % str(temp_ids[i]))
          query_results = list(cur.fetchall()[0])
          query_results.append(temp_similarities[i])
          query_results[2] = query_results[2].replace('api.','').replace('repos/','')
          return_array.append(query_results)
    
        return render_template("list_repositories.html", results = return_array)


    if method == "users":
        query_text = process_text(query_text)
        testing_vector = tfidf_vectorizer.transform([query_text])
        similarities = cosine_similarity(testing_vector,tfidf_matrix)[0]
#        similarities = linear_kernel(testing_vector,tfidf_matrix)[0]
        sorted_index = np.argsort(-1*similarities)
        sorted_similarities = similarities[sorted_index]
        sorted_ids = np.array(ids)[sorted_index]
        cur = db.cursor()
        start = 0
        cut_off = start
        for i in range(start, len(ids)):
            if sorted_similarities[i] < 0.01:
                cut_off = i
                break

        for i in range(start, cut_off):
            cur.execute("SELECT language FROM projects WHERE id="+str(sorted_ids[i])+";")
            query_results = cur.fetchall()

        temp_similarities = sorted_similarities[0:cut_off]
        temp_ids = sorted_ids[0:cut_off]
        sorted_index = np.argsort(-1*temp_similarities)
    
        temp_similarities = temp_similarities[sorted_index]
        temp_ids = temp_ids[sorted_index]

        new_cut_off = cut_off

        for i in range(start, cut_off):
            if temp_similarities[i] < 0.01:
                new_cut_off = i
                break


        return_array = []

        for i in range(start,min(10,new_cut_off)):
            cur.execute("SELECT id, name, url, language,description FROM projects WHERE id=%s;" % str(temp_ids[i]))
            query_results = list(cur.fetchall()[0])
            query_results.append(temp_similarities[i])
            query_results[2] = query_results[2].replace('api.','').replace('repos/','')
            return_array.append(query_results)
        cur = db.cursor()

        user_contributions = {}
        user_counts = {}
        for member in return_array:
            key = member[0]
            cur.execute("SELECT id, name, url, language,description FROM projects WHERE id=%s;" % str(key))
            query_results = list(cur.fetchall()[0])
            base_repo_id = query_results[0]
            cur.execute("SELECT DISTINCT COUNT(pull_request_id),head_repo_id FROM pull_requests INNER JOIN  pull_request_history  ON pull_requests.id=pull_request_id  WHERE action='merged' AND base_repo_id = %s GROUP BY head_repo_id;" %str(base_repo_id))
            query_results = list(cur.fetchall())

            for head_repo in query_results:
                if head_repo[1]:
                    cur.execute("SELECT owner_id FROM projects WHERE id=%s;"%head_repo[1])
                    temp_result = cur.fetchall()
                    if temp_result:
                        owner_id = temp_result[0][0]
                        user_counts.setdefault(owner_id,0)
                        user_counts[owner_id] += head_repo[0]
                        user_contributions.setdefault(owner_id,{})
                        user_contributions[owner_id].setdefault(key,0)
                        user_contributions[owner_id][key] += head_repo[0]

    
        output_to_html = []
        for key in sorted(user_contributions.keys(),key = lambda x: -user_counts[x]):
            cur.execute("SELECT id,login,name,email FROM users WHERE id=%s;"%key)
            data_point = cur.fetchall()[0]
            url = "http://github.com/"+data_point[1]
            final_data = data_point+(url,user_counts[key])
            output_to_html.append(final_data)

        return render_template("list_candidates.html", results = output_to_html)
            
    

        

@app.route('/list_repositories')
def list_repositories_f():
    if client.rate_limiting[0] < 3:
        return "exceeded API limit"
    repo_name = request.args.get('repo_name')

    try:
        repo = client.get_repo(repo_name)
    except Exception:
        return render_template('error.html')
    try:
        readme = repo.get_readme()
        txt = str(base64.b64decode(readme.content))
          
    except Exception:
        txt = ""
      
    txt = txt.replace("\\n","\n")
    txt = txt.replace("\\t","\t")
    txt = txt.replace("\\r","\n")

#    except Exception:
#        txt = ""

    txt = process_text(txt)
    if repo.description:
        description = repo.description.replace("\\n","\n")
    else:
        description = ""
    description = description.replace("\\t","\t")
    description = description.replace("\\r","\n")
    description = process_text(description)
    
    if repo.name:
        name = repo.name.replace("\\n","\n")
    else:
        name = ""
    name = name.replace("\\t","\t")
    name = name.replace("\\r","\n")

    name = process_text(name)
    testing_text = (description+" ")*1+(name+" ")*1+" ".join(txt.split(' ')[:140])

    testing_vector = tfidf_vectorizer.transform([testing_text])
    similarities = cosine_similarity(testing_vector,tfidf_matrix)[0]
    sorted_index = np.argsort(-1*similarities)
    sorted_similarities = similarities[sorted_index]
    sorted_ids = np.array(ids)[sorted_index]

    cur = db.cursor()
    cur.execute("SELECT url FROM projects WHERE id="+str(sorted_ids[0])+";")
    query_results = cur.fetchall()
    match = re.search(r"/([^\/]+)/([^\/]+)$",query_results[0][0])
    first_name = match.group(1)+"/"+match.group(2)
    if first_name == repo_name:
        start = 1
    else:
        start = 0
    start = 0
    cut_off = start
    for i in range(start, len(ids)):
        if sorted_similarities[i] < 0.01:
            cut_off = i
            break
    
    for i in range(start, cut_off):
        cur.execute("SELECT language FROM projects WHERE id="+str(sorted_ids[i])+";")
        query_results = cur.fetchall()
        if repo.language != query_results[0][0]:
            sorted_similarities[i] *= 0.5

    temp_similarities = sorted_similarities[0:cut_off]
    temp_ids = sorted_ids[0:cut_off]
    sorted_index = np.argsort(-1*temp_similarities)
    
    temp_similarities = temp_similarities[sorted_index]
    temp_ids = temp_ids[sorted_index]

    new_cut_off = cut_off

    for i in range(start, cut_off):
        if temp_similarities[i] < 0.01:
            new_cut_off = i
            break


    return_array = []

    for i in range(start,min(new_cut_off,1000)):
        cur.execute("SELECT id, name, url, language,description FROM projects WHERE id=%s;" % str(temp_ids[i]))
        query_results = list(cur.fetchall()[0])
        query_results.append(temp_similarities[i])
        query_results[2] = query_results[2].replace('api.','').replace('repos/','')
        return_array.append(query_results)
    
    return render_template("list_repositories.html", results = return_array)

@app.route('/list_candidates')
def list_candidates_f():
    cur = db.cursor()
    user_contributions = {}
    user_counts = {}
    for key in request.args:
        cur.execute("SELECT id, name, url, language,description FROM projects WHERE id=%s;" % str(key))
        query_results = list(cur.fetchall()[0])
        base_repo_id = query_results[0]
        cur.execute("SELECT DISTINCT COUNT(pull_request_id),head_repo_id FROM pull_requests INNER JOIN  pull_request_history  ON pull_requests.id=pull_request_id  WHERE action='merged' AND base_repo_id = %s GROUP BY head_repo_id;" %str(base_repo_id))
        query_results = list(cur.fetchall())
        for head_repo in query_results:
            if head_repo[1]:
                cur.execute("SELECT owner_id FROM projects WHERE id=%s;"%head_repo[1])
                temp_result = cur.fetchall()
                if temp_result:
                    owner_id = temp_result[0][0]
                    user_counts.setdefault(owner_id,0)
                    user_counts[owner_id] += head_repo[0]
                    user_contributions.setdefault(owner_id,{})
                    user_contributions[owner_id].setdefault(key,0)
                    user_contributions[owner_id][key] += head_repo[0]

    
    output_to_html = []
    for key in sorted(user_contributions.keys(),key = lambda x: -user_counts[x]):
        cur.execute("SELECT id,login,name,email FROM users WHERE id=%s;"%key)
        data_point = cur.fetchall()[0]
        url = "http://github.com/"+data_point[1]
        final_data = data_point+(url,user_counts[key])
        output_to_html.append(final_data)

    return render_template("list_candidates.html", results = output_to_html)
            
    
