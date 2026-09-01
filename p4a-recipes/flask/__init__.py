"""
Surcharge locale de la recette Flask de python-for-android.

Seule différence avec la recette amont : `markupsafe` est retiré de
`python_depends` et déplacé dans `depends`.

Pourquoi : p4a construit deux ensembles distincts dans graph.py, les paquets
compilés par recette (`build_order`) et ceux installés par pip
(`python_modules`), puis vérifie qu'ils sont disjoints :

    assert set(build_order).intersection(set(python_modules)) == set()

La recette amont déclare markupsafe dans `python_depends`, donc pip. Dès qu'on
lui fournit une recette locale (indispensable, cf. p4a-recipes/markupsafe), il
se retrouve dans les deux ensembles et p4a s'arrête sur une AssertionError.
Le déclarer dans `depends` le range du bon côté et garantit qu'il est construit
avant Flask.
"""

from pythonforandroid.recipe import PyProjectRecipe


class FlaskRecipe(PyProjectRecipe):
    version = '3.1.1'
    url = 'https://github.com/pallets/flask/archive/{version}.zip'
    depends = ['markupsafe']
    python_depends = ['jinja2', 'werkzeug', 'itsdangerous', 'click', 'blinker']


recipe = FlaskRecipe()
