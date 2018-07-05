import colors
from collections import Counter
import logging
import re
colors = colors.Colors()


class MetadataFetcher(object):
    def __init__(self, looker):
        self.looker = looker
        logging.config.fileConfig('logging.conf',
                                  disable_existing_loggers=False)
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_project_files(self, project=None):
        self.logger.info('Fetching projects, %s', locals())
        if project is None:
            self.logger.info('Fetching all project files')
            projects = self.looker.get_projects()
        else:
            self.logger.info('Fetching project files for project/%s', project)
            projects = self.looker.get_project(project)

        project_data = []
        for p in projects:
            project_files = self.looker.get_project_files(project=p['id'])

            project_data.append({
                    'name': p['id'],
                    'pr_mode': p['pull_request_mode'],
                    'validation_required': p['validation_required'],
                    'git_remote_url': p['git_remote_url'],
                    'files': project_files
            })
        self.logger.info('Fetching Complete')
        return project_data

    # function that returns list of model definitions or model names (with
    # verbose 0 or 1 respectively) Allows the user to specify a project name,
    # a model name or nothing at all. project paramater is a string while model
    # parameter is a list
    def get_models(self, project=None, model=None, verbose=0, scoped_names=0):
        self.logger.info('Fetching models, %s', locals())
        if project is None and model is None:
            self.logger.info('Fetching all models')
            models = self.looker.get_models()
        elif project is not None and model is None:
            # if no parameters are specified
            self.logger.info('Fetching all models for project/%s', project)
            response = self.looker.get_models()
            models = list(filter(lambda x: x['project_name'] == project, response))
            if not models:
                self.logger.info('Project not found')
                raise Exception('Project not found')
        elif project is not None and model is not None:
            # if both project and model paramaters are specified
            self.logger.info('Warning: Project parameter ignored. \
                             Model names are unique across projects.')
            models = [self.looker.get_model(model)]
        else:
            # if project parameter wasn't passed but model was.
            self.logger.info('Fetching model/%s', model)
            models = self.looker.get_model(model_name=model)

        models = list(filter(lambda x: x['has_content'] is True, models))
        if verbose == 0:
            models = [(m['project_name']+".")*scoped_names+m['name'] for m in models]
        self.logger.info('Fetch Complete')
        return models

    def get_used_models(self, timeframe=90, min_queries=0):
        self.logger.info('Fetching used models from i__looker, %s', locals())
        timeframe = str(timeframe) + ' days'
        min_queries = '>=' + str(min_queries)
        body = {
                "model": "i__looker",
                "view": "history",
                "fields": ["query.model", "history.query_run_count"],
                "filters": {"history.created_date": timeframe,
                            "query.model": "-i^_^_looker",
                            "history.query_run_count": min_queries
                            },
                "limit": "50000"
                }

        response = self.looker.run_inline_query("json", body)

        x = {}
        for r in response:
            x[r['query.model']] = r['history.query_run_count']
        self.logger.info('Fetch Complete')
        return(x)

    # errors have to be handled more downstream if explore does not exist due
    # to bug #32748
    def get_explores(self, model=None, explore=None, scoped_names=0,
                     verbose=0):
        self.logger.info('Fetching explores, %s', locals())
        explores = []
        if explore is not None:
            self.logger.info('Fetching explore/%s', explore)
            e = self.looker.get_explore(model_name=model, explore_name=explore)
            if e:
                explores.extend(e)
        else:
            self.logger.info('Fetching all explores')
            models = self.get_models(model=model, verbose=1)
            for mdl in models:
                for e in mdl['explores']:
                    if verbose == 1:
                        explores.extend(self.looker.get_explore(mdl['name'],
                                                                e['name']))
                    else:
                        explores.append((mdl['name'], e['name']))
        self.logger.info('Fetch Complete')
        return explores

    def get_explore_fields(self, explore=None, scoped_names=0):
        self.logger.info('Fetching exposed explore fields')
        fields = []
        for dimension in explore['fields']['dimensions']:
            if dimension['hidden'] is not True:
                fields.append((explore['model_name']+'.'
                              + explore['name']+'.')*scoped_names
                              + dimension['name'])
        for measure in explore['fields']['measures']:
            if measure['hidden'] is not True:
                fields.append((explore['model_name']+'.'
                              + explore['name']+'.')*scoped_names
                              + measure['name'])
        for fltr in explore['fields']['filters']:
            if fltr['hidden'] is not True:
                fields.append((explore['model_name']+'.'
                              + explore['name']+'.')*scoped_names
                              + fltr['name'])
        self.logger.info('Fetch Complete')
        return list(set(fields))

    def get_unused_explores(self, model=None, timeframe=90, min_queries=0):
        self.logger.info('Fetching unused explores, %s', locals())
        used_explores = self.get_used_explores(model=model,
                                               timeframe=timeframe,
                                               min_queries=min_queries)
        used_explores = used_explores.keys()
        all_explores = self.get_explores(model=model)
        all_explores = [i[1] for i in all_explores]
        unused_explores = list(set(all_explores) - set(used_explores))
        self.logger.info('Fetch Complete')
        return unused_explores

    # function that runs i__looker query and returns fully scoped fields used
    # remember explore names are not unique, filter on model as well
    # query.explore is the actual explore name
    # query.model is the model
    # query.fields are is view.field (view is view name used in the explore)
    # to uniquely identify fields, explore.view.field should be used,
    # or even better, model.explore.view.field
    def get_used_explore_fields(self, model=None, explore=None, timeframe=90,
                                min_queries=0):
        self.logger.info('Fetching exposed explore fields, %s', locals())
        m = model.replace('_', '^_') + ',' if model is not None else ''
        m += "-i^_^_looker"
        e = ','.join(explore).replace('_', '^_')
        min_queries = '>=' + str(min_queries)
        timeframe = str(timeframe) + ' days'
        body = {
                "model": "i__looker",
                "view": "history",
                "fields": ["query.model", "query.view",
                           "query.formatted_fields",
                           "query.formatted_filters", "query.sorts",
                           "query.formatted_pivots",
                           "history.query_run_count"],
                "filters": {"history.created_date": timeframe,
                            "query.model": m,
                            "query.view": e,
                            "history.query_run_count": min_queries},
                "limit": "50000"
        }
        # returns only fields used from a given explore
        response = self.looker.run_inline_query("json", body)

        formatted_fields = []
        for row in response:
            fields = []
            explore = row['query.view']
            model = row['query.model']
            run_count = row['history.query_run_count']
            fields.extend(re.findall(r'(\w+\.\w+)',
                                     str(row['query.formatted_fields'])))
            fields.extend(re.findall(r'(\w+\.\w+)',
                                     str(row['query.formatted_filters'])))
            fields.extend(re.findall(r'(\w+\.\w+)',
                                     str(row['query.formatted_pivots'])))
            fields.extend(re.findall(r'(\w+\.\w+)',
                                     str(row['query.sorts'])))
            formatted_fields.extend([model+'.'+explore+'.'+field+'.'
                                     + str(run_count) for field in fields])

        field_name = []
        field_use_count = []
        for row in formatted_fields:
            field = '.'.join(row.split('.')[:-1])  # remove the count
            field_name.append(field)  # model.explore.view scoped
            count = int(row.split('.')[-1])
            field_use_count.append({
                'field_name': field,
                'count': count
            })

        c = Counter()

        for value in field_use_count:
            c[value['field_name']] += value['count']
        self.logger.info('Fetch Complete')
        return dict(c)

    def get_used_explores(self, model=None, explore=None,
                          timeframe=90, min_queries=0):
        self.logger.info('Fetching used explores, %s', locals())
        timeframe = str(timeframe) + ' days'
        min_queries = '>=' + str(min_queries)
        m = model.replace('_', '^_') + ',' if model is not None else ''
        body = {
                "model": "i__looker",
                "view": "history",
                "fields": ["query.view", "history.query_run_count"],
                "filters": {"history.created_date": timeframe,
                            "query.model": m,
                            "history.query_run_count": min_queries,
                            "query.view": explore
                            },
                "limit": "50000"
                }

        response = self.looker.run_inline_query("json", body)

        x = {}
        for r in response:
            x[r['query.view']] = r['history.query_run_count']
        self.logger.info('Fetch Complete')
        return(x)

    def test_git_connection(self, project):
        # enter dev mode
        self.looker.update_session(mode='dev')
        # obtain tests available
        tests = [test['id'] for test in self.looker.git_connection_tests(project_id=project)]
        verbose_result = []
        fail_flag = 0
        for idx, test in enumerate(tests):
            s = '({}/{}) {}'.format(idx+1, len(tests), test)
            r = self.looker.run_git_connection_test(project_id=project, test_id=test)
            verbose_result.append(colors.format(s, r['status']))
            #colors.OKGREEN + s + colors.ENDC + '\n' if r['status']=='pass' else colors.FAIL + s + colors.ENDC + '\n'
            if r['status'] != 'pass':
                fail_flag = 1
        verbose_result = ('\n').join(verbose_result)
        result = verbose_result if fail_flag == 1 else 'OK'
        return result
