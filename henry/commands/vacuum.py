#!/usr/local/bin/python3
import logging
from henry.modules import styler
from henry.modules.fetcher import Fetcher as fetcher
import re
import sys


class Vacuum(fetcher):
    def __init__(self, looker):
        super(Vacuum,self).__init__(looker)
        self.vacuum_logger = logging.getLogger('vacuum')

    def vacuum(self, **kwargs):
        p = kwargs['project'] if 'project' in kwargs.keys() else None
        m = kwargs['model'] if 'model' in kwargs.keys() else None
        format = 'plain' if kwargs['plain'] else 'psql'
        headers = '' if kwargs['plain'] else 'keys'
        if kwargs['which'] == 'models':
            self.vacuum_logger.info('Vacuuming Models')
            params = {k: kwargs[k] for k in {'project',
                                             'model',
                                             'timeframe',
                                             'min_queries'}}
            self.vacuum_logger.info('vacuum models params=%s', params)
            result = self._vacuum_models(project=p,
                                         model=m,
                                         min_queries=kwargs['min_queries'],
                                         timeframe=kwargs['timeframe'])
        if kwargs['which'] == 'explores':
            self.vacuum_logger.info('Vacuuming Explores')
            params = {k: kwargs[k] for k in {'model',
                                             'explore',
                                             'timeframe',
                                             'min_queries'}}
            self.vacuum_logger.info('vacuum explores params=%s', params),
            result = self._vacuum_explores(model=m,
                                           explore=kwargs['explore'],
                                           min_queries=kwargs['min_queries'],
                                           timeframe=kwargs['timeframe'])
        if kwargs['which'] == 'fields':
            self.vacuum_logger.info('Vacuuming Fields')
            params = {k: kwargs[k] for k in {'model',
                                             'explore',
                                             'timeframe',
                                             'min_queries'}}
            self.vacuum_logger.info('vacuum fields params=%s', params),
            result = self._vacuum_fields(model=m,
                                           explore=kwargs['explore'],
                                           min_queries=kwargs['min_queries'],
                                           timeframe=kwargs['timeframe'])
        self.vacuum_logger.info('Vacuum Complete')
        result = styler.tabulate(result, headers=headers,
                                 tablefmt=format, numalign='center')
        return result

    def _vacuum_models(self, project=None, model=None, timeframe=90,
                       min_queries=0):
        if model is None:
            model = fetcher.get_models(self, project=project)
        else:
            model = model.split()
        used_models = fetcher.get_used_models(self, timeframe)
        info = []
        for m in model:
            explores = [e['name'] for e in fetcher.get_explores(self, model=m,
                                                                verbose=1)]
            unused_explores = fetcher.get_unused_explores(self, m,
                                                          timeframe,
                                                          min_queries)
            query_run_count = used_models[m] if m in used_models.keys() else 0
            unused_explores = ('\n').join(unused_explores)
            info.append({
                        'model': m,
                        'unused_explores': unused_explores or 'None',
                        'model_query_run_count': query_run_count})

        return info

    def _vacuum_fields(self, model=None, explore=None, timeframe=90,
                        min_queries=0):
        explores = fetcher.get_explores(self,
                                        model=model,
                                        explore=explore,
                                        verbose=1)
        info = []
        master_exposed_fields = set()
        master_used_fields = set()
        distinct_views = set()
        progress = 1
        for e in explores:
            print('Analyzing {}.{}, {} of {} explores'.format(e['model_name'],
                                                                  e['name'],
                                                                  progress,
                                                                  len(explores)))
            # get field usage from i__looker using all the views inside explore
            # returns fields in the form of model.explore.view.field
            _used_fields = fetcher.get_used_explore_fields(self,
                                                           e['model_name'],
                                                           e['scopes'],
                                                           timeframe,
                                                           min_queries)
            used_fields = list(_used_fields.keys())

            # get field picker fields in the form of model.explore.view.field
            exposed_fields = fetcher.get_explore_fields(self,
                                                        explore=e,
                                                        scoped_names=1)
            _unused_fields = set(exposed_fields) - set(used_fields)

            # Get fields used in joins
            for join in e['joins']:
                if join['sql_on'] is not None:
                    f = re.findall('\{(.*?)\}',join['sql_on'])
                    for field in f:
                        master_used_fields.add(field)
                        distinct_views.add(field.split('.')[0])
            #Get used fields
            for field in used_fields:
                field = '.'.join(field.split('.')[2:])
                master_used_fields.add(field)
                distinct_views.add(field.split('.')[0])
            #Get all fields
            for field in exposed_fields:
                #strip out the model and explore
                field = '.'.join(field.split('.')[2:])
                master_exposed_fields.add(field)
                distinct_views.add(field.split('.')[0])
            progress += 1

        # Fields to ignore if they contain the following:
        ignore_list = ['week','quarter','year','month','raw','date','time']

        # Get all unused fields and then organize them by their view
        master_unused_fields = master_exposed_fields-master_used_fields
        for view in sorted(list(distinct_views)):
            if any(char.isdigit() for char in view):
                continue
            unused_fields = []
            for field in master_unused_fields:
                # always keep id fields and basic count fields
                field_name = field.split('.')[1]
                if field_name == 'id' or field_name == 'count' or 'id' in field_name.split('_'):
                    continue
                elif any(ignore in field for ignore in ignore_list):
                    continue
                if field.split('.')[0] == view:
                    unused_fields.append(field)
            unused_fields = ('\n').join(unused_fields)
            if unused_fields is not None:
                info.append({
                            'view': view,
                            'unused_fields': unused_fields
                            })
        if not info:
            self.vacuum_logger.error('No matching explores found')
            raise Exception('No matching explores found')
        return info

    def _vacuum_explores(self, model=None, explore=None, timeframe=90,
                         min_queries=0):
        explores = fetcher.get_explores(self,
                                        model=model,
                                        explore=explore,
                                        verbose=1)
        info = []
        for e in explores:
            # get field usage from i__looker using all the views inside explore
            # returns fields in the form of model.explore.view.field
            _used_fields = fetcher.get_used_explore_fields(self,
                                                           e['model_name'],
                                                           e['scopes'],
                                                           timeframe,
                                                           min_queries)
            used_fields = list(_used_fields.keys())
            # get field picker fields in the form of model.explore.view.field
            exposed_fields = fetcher.get_explore_fields(self,
                                                        explore=e,
                                                        scoped_names=1)
            _unused_fields = set(exposed_fields) - set(used_fields)

            # remove scoping
            all_joins = set(e['scopes'])
            all_joins.remove(e['name'])
            used_joins = set([i.split('.')[2] for i in used_fields])

            _unused_joins = list(all_joins - used_joins)
            unused_joins = ('\n').join(_unused_joins) or 'N/A'

            # only keep fields that belong to used joins (unused joins fields
            # don't matter) if there's at least one used join (including the
            # base view). else don't match anything
            temp = list(used_joins)
            temp.append(e['name'])
            pattern = ('|').join(temp) or 'ALL'
            unused_fields = []
            if pattern != 'ALL':
                for field in _unused_fields:
                    f = re.match(r'^({0}).*'.format(pattern),
                                 '.'.join(field.split('.')[2:]))
                    if f is not None:
                        unused_fields.append(f.group(0))
                unused_fields = sorted(unused_fields)
                unused_fields = ('\n').join(unused_fields)
            else:
                unused_fields = styler.color.format(pattern,
                                                    'fail',
                                                    'color')
            info.append({
                        'model': e['model_name'],
                        'explore': e['name'],
                        'unused_joins': unused_joins,
                        'unused_fields': unused_fields
                        })
        if not info:
            self.vacuum_logger.error('No matching explores found')
            raise Exception('No matching explores found')
        return info
